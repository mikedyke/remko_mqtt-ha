"""Module for Remko MQTT heating curve (register 1251) conversion.

Port of the SmartWeb UI's own handling of the "curve_t" register type
(updateCurve() and shmvalue2hex() in smt.min.js). The register holds four
16-bit elements, in the UI's array order:

    0: Fusspunkt (flow temp. at +20 °C outside)  x10, range 15.0-35.0 °C
    1: Norm-Vorlauftemperatur                    x10, range 20.0-90.0 °C
    2: Norm-Ruecklauftemperatur                  x10, range 10.0-70.0 °C
    3: Heating curve exponent                    x100, range 1.00-1.40

Only elements 0 and 1 are settings: the UI recomputes elements 2 and 3 from
the Norm-Vorlauftemperatur on every edit. The hex payload serializes the
elements last to first, two bytes each (big-endian per element).
"""

import logging

_LOGGER = logging.getLogger(__name__)

_RAW_RANGES = ((150, 350), (200, 900), (100, 700), (100, 140))

FUSSPUNKT_MIN = _RAW_RANGES[0][0] / 10
FUSSPUNKT_MAX = _RAW_RANGES[0][1] / 10
NORM_VORLAUF_MIN = _RAW_RANGES[1][0] / 10
NORM_VORLAUF_MAX = _RAW_RANGES[1][1] / 10
STEP = 0.5


def decode_heizkurve(value: str) -> dict[str, float] | None:
    """Convert a 16-character register 1251 hex string into its four values."""
    if not value or len(value) != 16:
        _LOGGER.error("Unexpected heating curve payload: %s", value)
        return None
    try:
        exponent, ruecklauf, vorlauf, fusspunkt = (
            int(value[pos : pos + 4], 16) for pos in range(0, 16, 4)
        )
    except ValueError:
        _LOGGER.error("Invalid heating curve payload: %s", value)
        return None
    return {
        "fusspunkt": fusspunkt / 10,
        "norm_vorlauftemperatur": vorlauf / 10,
        "norm_ruecklauftemperatur": ruecklauf / 10,
        "exponent": exponent / 100,
    }


def encode_heizkurve(fusspunkt: float, norm_vorlauftemperatur: float) -> str:
    """Build the register 1251 hex string exactly as the SmartWeb UI does."""

    def clamp(index: int, raw: int) -> int:
        low, high = _RAW_RANGES[index]
        return min(max(low, raw), high)

    fp = min(max(FUSSPUNKT_MIN, round(fusspunkt * 10) / 10), FUSSPUNKT_MAX)
    nv = min(
        max(NORM_VORLAUF_MIN, round(norm_vorlauftemperatur * 10) / 10),
        NORM_VORLAUF_MAX,
    )

    nr = nv - (0.175 * nv + 3.5)
    # Powers by multiplication, not pow(): for 0.5-step inputs every
    # intermediate is exact, so the result can't depend on the platform libm.
    nv2 = nv * nv
    nv3 = nv2 * nv
    nv4 = nv3 * nv
    nv5 = nv4 * nv
    exponent = (
        -0.445691
        + 0.0853006 * nv
        - 0.00166865 * nv2
        + 1.67111e-5 * nv3
        - 8.59587e-8 * nv4
        + 1.81621e-10 * nv5
    )

    elements = (
        clamp(0, int(10 * fp)),
        clamp(1, int(10 * nv)),
        clamp(2, int(10 * nr)),
        clamp(3, int(100 * exponent)),
    )
    return "".join(f"{element & 0xFFFF:04x}" for element in reversed(elements))
