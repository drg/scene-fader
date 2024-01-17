"""The SceneFader integration."""
from __future__ import annotations

from homeassistant.core import State
from homeassistant.helpers.state import async_reproduce_state, state_as_number

from .const import DOMAIN


def _interpolate_value(lower_value, upper_value, position):
    if upper_value is None:
        return lower_value
    elif lower_value is None:
        return upper_value
    elif isinstance(lower_value, int) and isinstance(upper_value, int):
        return round(lower_value + (upper_value - lower_value) * position)
    elif isinstance(lower_value, float) and isinstance(upper_value, float):
        return round(lower_value + (upper_value - lower_value) * position)
    else:
        return upper_value if position > 0.5 else lower_value

def _interpolate_states(lower_state, upper_state, position):
    assert lower_state.entity_id == upper_state.entity_id

    interpolated_state = State(lower_state.entity_id, lower_state.state, dict(lower_state.attributes))
    interpolated_state.attributes = lower_state.attributes.copy()

    try:
        # If the state is one of the special strings (e.g. "on", "open", "locked") and
        # one of the states evaluates to 1, then we use that state's string value. This
        # is to ensure that lights stay on except when setting precisely to the off
        # state.
        lower_state_value = state_as_number(lower_state)
        upper_state_value = state_as_number(upper_state)
        if isinstance(lower_state.state, str) or isinstance(upper_state.state, str):
            if lower_state_value == 1:
                state_value = lower_state.state
            else:
                state_value = upper_state.state
        else:
            state_value = _interpolate_value(lower_state.state, upper_state.state, position)

    except ValueError:
        state_value = _interpolate_value(lower_state.state, upper_state.state, position)

    interpolated_state.state = state_value

    for attribute in set(lower_state.attributes) & set(upper_state.attributes):
        lower_value = lower_state.attributes[attribute]
        upper_value = upper_state.attributes[attribute]
        print (f"Interpolating {attribute} between types {type(lower_value)} and {type(upper_value)}")
        print (f"Interpolating between {lower_value} and {upper_value}")
        interpolated_state.attributes[attribute] = _interpolate_value(lower_value, upper_value, position)

    return interpolated_state

def setup(hass, config):
    """Set up is called when Home Assistant is loading our component."""

    async def async_handle_turn_on(call):
        """Handle the service call."""
        scenes = call.data.get("scenes", {})
        position = call.data.get("position", 0.5)

        assert position >= 0 and position <= 1
        assert len(scenes) >= 2
        assert all([x['interval'] >= 0 and x['interval'] <= 1 for x in scenes])
        # assert all([x['entity_id'] in hass.data['scene'].entities for x in scenes])

        print ("Scenes:", scenes)
        print ("Position:", position)

        interval_map = {x['interval'] : hass.data['scene'].get_entity(x['entity_id']) for x in scenes}

        # Ensure lower and upper bounds are in the map.
        interval_map[0] = interval_map[min(interval_map.keys())]
        interval_map[1] = interval_map[max(interval_map.keys())]

        if position in interval_map:
            await interval_map[position].async_activate()
            return

        sorted_intervals = sorted(interval_map.keys())

        lower_interval = [x for x in sorted_intervals if x <= position][-1]
        upper_interval = [x for x in sorted_intervals if x >= position][0]

        lower_scene = interval_map[lower_interval]
        upper_scene = interval_map[upper_interval]

        lower_config = lower_scene.scene_config
        upper_config = upper_scene.scene_config

        scaled_interval = (position - lower_interval) / (upper_interval - lower_interval)

        states_to_interpolate = set(lower_config.states) & set(upper_config.states)
        interpolated_states = []

        for state in states_to_interpolate:
            lower_value = lower_config.states[state]
            upper_value = upper_config.states[state]
            interpolated_states.append(_interpolate_states(lower_value, upper_value, scaled_interval))

        print ("Interpolated states:", interpolated_states)
        await async_reproduce_state(hass, interpolated_states, context=call.context)

    hass.services.register(DOMAIN, "turn_on", async_handle_turn_on)

    # Return boolean to indicate that initialization was successful.
    return True
