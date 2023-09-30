# Changelog

## 2.2.7
- [#590](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/590) (Temporary?) workaround for PRAW websocket error; bumped praw versions
- [#572](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/572) `/cco complete` now resolves carrier search term against carriers db instead of missions db. (This will make it consistent with all other instances of using a specific search term to look for a carrier.)
- Converted bot-spam notices for `/create_community_channel`, `/restore_community_channel`, `/remove_community_channel` to embeds
- [#575](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/575) Error handling for channel deletion sequence upon mission complete
- [#565](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/565) Update carrier channel mission embed creation to use guild user avatar rather than global
- [#564](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/564) Archiving community channels now checks for successful permission sync and retries on failure
- [#563](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/563) Fixed month not updating for image choice purposes
- [#566](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/566) Fixed unloads showing carrier supply as if it was station demand
- [#561](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/561) `m.complete` now includes an interactible link for `/mission complete`
- [#560](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/560) Verify Member now includes a jumpurl in the bot-spam notification


## 2.2.6
- [#50](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/50) Logic to create commodities table from scratch
- Logic to add new commodities
- [#580](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/580) Check background tasks aren't running before starting them from `on_ready`
- [#573](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/573) Prevent bots from being nominated for Community Pillar 


## 2.2.5
- More minor error/status report tidy-ups


## 2.2.4
- [#554](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/554) Corrected time on mission generator channel lock alert.
- [#556](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/556) Wine loads will no longer ping the BubbleWineLoader role even if the Select Menu is used to attempt to do so.


## 2.2.3
- [#548](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/548) Errors on commodity search during mission generation now handled by the global error handler.
- [#550](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/550) Role grant/removal context menu commands should now be more resilient to Discord lag.
- [#549](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/549) Moved most CCOCommands errors to error handler

Error message tweaks:

- Various small tweaks to most error message formats
- User-facing text now generally reads "❌" intead of "ERROR"
- New custom error class: CustomError
 - takes a custom message to return to the user
 - response can be set private or public


## 2.2.2
- [#545](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/545) `/cco load` and `/cco unload` now have the option to send to Discord at the top, with a note that it is mandatory.
 - Using it no longer sends exclusively to Discord, ignoring other selections.
- [#544](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/544) Training and Live missions will now only attempt to re-use channels in the correct category.
- [#541](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/541) Using `/carrier_add` now also outputs the code needed to add the carrier to stockbot.
- [#540](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/540) Reason given for mission failure (or success!) now included in bot spam notification.
- [#543](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/543) Added pad size to the station info embed.
- [#513](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/513) Display names and usernames will now be added in parentheses for nominees shown using `/cp_nomination_details` or `/cp_nominees_list`.
- The `this mission channel will be removed in...` notice now clarifies removal will take place `unless a new mission is started.`


## 2.2.1

- [#533](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/533) `Make Full CCO` now removes Trainee, Recruit, and ACO roles from target user
- [#534](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/534) Notify bot-spam on role grants and removals


## 2.2

New commands:
- [#473](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/473) App command `Toggle Event Organiser` to grant Verified Member role, usably by Community Mentors, Mods, and Admins.
- [#475](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/475) App command `Verify Member` to grant or remove Event Organiser role, usably by Community Mentors, Mods, and Admins.
- [#474](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/474) App command `Make CCO Trainee` to grant or remove the CCO Trainee role, usable by CCO Mentors, Mods, and Admins.
- [#474](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/474) App command `Make Full CCO` to grant the Certified Carrier and P.T.N. Fleet Reserve roles, usable by CCO Mentors, Mods, and Admins.

Other changes:

- [#529](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/529) EDMC OFF text above channel alert is now an image
 - random shh/secret/ninja gifs used in embed in place of previous superhero images


## 2.1.4

- [#521](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/521) `Pads` parameter will be vastly more forgiving of acceptable input (`/cco load`, `/cco unload`, `/cco edit`)
- [#523](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/523) The channel removal timer for `/mission complete` "Failed" now uses hammertime.
- [#520](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/520) Channel unlocks will now check if the lock is acquired before attempting to release.
- [#524](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/524) Webhook mission image will now change if mission type is changed with `/cco edit`.
 - also made image replacement method more resilient to Discord being fucking weird
- temp images used during `/cco edit` are now properly cleaned up afterwards


## 2.1.3

- [#507](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/507) Re-implemented startup check for orphaned mission channels
- Added logging to bot-spam of trade channel deletions
- [#516](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/516) Increased view timeouts to 5 minutes from 30 seconds (button view) and 2 minutes (select view) respectively
- [#517](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/517) Mission type (loading/unload) and mission message can now be edited with `/cco edit`


## 2.1.2

- [#505](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/505) Added dynamic channel locks
- #504 Redesigned `m.unlock_override`, is now `/admin_release_channel_lock` and takes channel lock name as parameter


## 2.1.1

- Removed channel_cleanup table from missions.db and related code
- [#508](https://github.com/PilotsTradeNetwork/MissionAlertBot/issues/508) Fixed incorrect timer for final channel deletion


## 2.1.0

Refactoring:

- Split `MissionGenerator.py` into `MissionGenerator.py` and `MissonCleaner.py`
- Major changes to the internal structure of the mission generator
    - Misison generation is now more resilient to errors and communicates better when something goes wrong
- Added `Commodities.py` in preparation for adding a method to build the Commodities database from scratch
- Added custom errors for interaction role and channel checks, and called them via the global error handler
- More errors handled elegantly
- More helpful notifications to bot-spam
- Many bot-spam messages converted to embeds
- Many response messages converted to embeds
- Many small changes here and there

Removed commands:
- `loadlegacy`, `unloadlegacy` have been removed
- legacy support has been removed
- `loadrp`, `unloadrp` have been removed

Changed commands:
- `load` and `unload` are now `/cco load` and `/cco unload` respectively
    - added describes to all parameters
    - added autocomplete for common commodities and pad size
    - ETA and RP text have been merged into the new "Message" feature:
        - "Message" is entered via Modal and sent to Discord destinations in a separate embed
    - buttons or select menu options for sends, replacing chat letter entry
        - note **you can SCROLL the select menu** to reveal additional options
    - added icons for send status embeds
    - completely new embed format for Discord
    - added ability to send via webhook
    - tweaks to Reddit format
    - demand/supply is now entered as an int/float (i.e. without the "k"), and is subject to validation
- `done` is now `/cco complete`. `/cco done` remains as an alias, for now
    - `/cco complete` now has optional parameters for whether the mission was `Completed` or `Failed`, with autocomplete, as well as for an explanation message
        - by default, status is assumed to be `Completed`
    - many small changes to how `/cco complete` reports
- `carrier_image` is now `/cco image`
- `m.complete` is now `/mission complete`
    - no more option to add a message as an argument
    - button menu asks user whether mission completed or cannot be completed
    - clicking unable to complete prompts user for an explanation message
- `/mission` is now `/mission information`
- `m.unlock_override` deletion check temporarily disabled.

New commands:
- `/cco webhook add` - CCO only - used to add a webhook to that CCO's personal list
- `/cco webhook view` - CCO only - shows their webhooks
- `/cco webhook delete` - CCO only - used to remove a webhook from their list
- `/cco edit` - CCO only - used to edit an in-progress mission. Presently only the original interaction parameters can be edited (i.e. the fields added via slash command). Editing message and mission type will be implemented in a future update.
- `/admin_delete_mission` - Admin only - used to manually remove a mission from the database (without cleanup). Intended for unresolvable error situations only.
- added **training mode** to `/cco load` and `/cco unload`. This will not affect webhooks but will send discord alerts to the new training channels, and reddit posts to the testing subreddit. Webhooks will be sent as normal, but it's expected trainees will add a training webhook anyway.

Other:
- When channel deletion is in its final 10 second countdown, a notice will appear in the mission-generator to warn that deletion is in progress and the channel lock is acquired. It is strongly advised not to attempt to "send" missions during this brief window. The message is removed once the lock is released.
- Automatically update PTN logos used by the bot during June.


## 2.0.0

Refactoring:

- Refactored the bot into standardised directory structure
- Refactored commands into Cogs
- Refactored auxiliary functions into modules
- New global error handlers for interactions and text commands respectively
- Implemented setup.py, the bot is now installed via `pip install -e.`
- Cleaned up requirements
- Removed interaction sync listener, replaced with command
    - sync is a high intensity action, best practice is to only do it when needed
- Added persistant data directory for use when containerised
    - this contains all carrier images, carrier backup images, and community channel images, as well as all database, database dump, and database backups
- Many small improvements to code
- Many, many more improvements to do

New environment variables:

- `PTN_MAB_DATA_DIR` - specifies the path to the `/data` directory where the bot stores all mutable files (databases, carrier images, community channel thumbnails)
- `PTN_MAB_RESOURCE_DIR` - specifies the path to the `/resource` directory which houses static non-Python files (default carrier images, mission template images, edmc off images, and fonts)

New commands:

- `/greet` - functionally identical to m.ping but as a slash command
- `m.sync` - syncs interactions with the server
    - this has to be done any time an interaction is added, removed, or has its definition changed

Changed commands

- `nom_count` is now `/cp_nominees_list`, and is ephemeral with the option to broadcast to channel
- `nom_delete` is now `/cp_delete_nominee_from_database`, and uses button confirmations
- `nom_details` is now `/cp_nomination_details`, and is ephemeral with the option to broadcast to channel
- `carrier_add` is now `/carrier_add`
- `carrier_delete` is now `/carrier_delete`, and uses button confirmations
- many slash commands have had descriptions added to their parameters
- mission generator returnflag has been (temporarily) removed, making error recovery less graceful (but still robust)
- some commands which usually take a while now have a "MissionAlertBot is typing..." status
    - this is in the experimental stages and needs to be properly tweaked