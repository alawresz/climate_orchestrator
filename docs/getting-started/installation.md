# Installation

## Via HACS (recommended)

[![Open your Home Assistant instance and add this repository to HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=alawresz&repository=climate_orchestrator&category=integration)

1. Click the button above (it opens HACS with this repository pre-filled), or add
   it manually in HACS → **⋮ → Custom repositories**:
   `https://github.com/alawresz/climate_orchestrator`, category **Integration**.
2. Search for **Climate Orchestrator** in HACS, download it, then **fully
   restart** Home Assistant.
3. **Settings → Devices & Services → Add Integration → "Climate Orchestrator"**.

## Manual

1. Copy `custom_components/climate_orchestrator/` into your Home Assistant
   configuration's `custom_components/` directory:

    ```
    <config>/custom_components/climate_orchestrator/
    ```

2. **Fully restart** Home Assistant (a new integration is only discovered on
   startup; "reload" is not enough). On first start HA installs `scipy`.

3. **Settings → Devices & Services → Add Integration → "Climate Orchestrator"**, then
   select your TRVs, ACs, and (optionally) an outdoor sensor, a weather entity,
   and your own whole-home average temperature/humidity sensors — see
   [First setup](first-setup.md) for a walkthrough of every field.

## Changing the configuration later

You can change the selected devices — and every other setup field, including
the advanced TRV name hints — later via the integration's **Configure**
(options) dialog. Each field is explained in
[First setup](first-setup.md).

## Upgrading

Upgrade through HACS as usual (download the new version, then restart Home
Assistant). To test prereleases, enable *Show beta versions* on the integration
in HACS. All tunables and learned state (MPC models, adaptive values) persist
across restarts, so an upgrade resumes where it left off.

## Removal

1. Go to **Settings → Devices & services → Climate Orchestrator**, open the
   entry's menu (⋮) and choose **Delete**. The integration's persisted learned
   state (MPC models, adaptive values) is cleaned up automatically.
2. Remove the repository from HACS (or delete
   `custom_components/climate_orchestrator/` for a manual install) and restart
   Home Assistant.
3. Your TRVs and ACs simply stop being orchestrated — they keep their last
   commanded state and return to manual control.

Next: [First setup](first-setup.md)
