import sys

import zip2info


def test_lookup() -> None:
    assert zip2info.timezone("90210") == "America/Los_Angeles", "Failed 90210"
    assert zip2info.timezone("10001") == "America/New_York", "Failed 10001"
    assert zip2info.timezone("60601") == "America/Chicago", "Failed 60601"

    coords = zip2info.coordinates("90210")
    assert coords is not None, "Failed 90210 coordinates"
    lat, lon = coords
    assert 30 < lat < 40, "Unexpected latitude for 90210"
    assert -125 < lon < -115, "Unexpected longitude for 90210"

    assert zip2info.timezone("00000") is None, "Failed unknown"

    print("Smoke test passed!")


if __name__ == "__main__":
    try:
        test_lookup()
    except Exception as e:
        print(f"Test failed: {e}")
        sys.exit(1)
