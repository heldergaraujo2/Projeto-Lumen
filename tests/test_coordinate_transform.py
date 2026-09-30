from __future__ import annotations

import pytest

from app.computer_control.coordinates import CoordinateSpace, CoordinateTransform


def test_observation_coordinates_map_to_negative_windows_virtual_desktop() -> None:
    transform = CoordinateTransform(
        CoordinateSpace.OBSERVATION,
        origin_x=-1920,
        origin_y=0,
    )

    assert transform.to_windows_screen(78, 1061) == (-1842, 1061)


def test_primary_monitor_observation_origin_maps_without_x_shift() -> None:
    transform = CoordinateTransform(
        CoordinateSpace.OBSERVATION,
        origin_x=0,
        origin_y=0,
    )

    assert transform.to_windows_screen(78, 1061) == (78, 1061)


def test_windows_screen_coordinates_are_not_converted_twice() -> None:
    transform = CoordinateTransform(CoordinateSpace.WINDOWS_SCREEN)

    assert transform.to_windows_screen(-1842, 1061) == (-1842, 1061)


def test_windows_screen_space_rejects_nonzero_observation_origin() -> None:
    with pytest.raises(ValueError, match="cannot carry"):
        CoordinateTransform(
            CoordinateSpace.WINDOWS_SCREEN,
            origin_x=-1920,
        )


def test_metadata_is_explicit_and_serializable() -> None:
    transform = CoordinateTransform(
        CoordinateSpace.OBSERVATION,
        origin_x=-1920,
        origin_y=0,
    )

    assert transform.metadata() == {
        "coordinate_space": "observation",
        "coordinate_origin_x": -1920,
        "coordinate_origin_y": 0,
    }
