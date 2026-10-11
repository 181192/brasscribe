"""The names and the number every app shares with the engine.

The pairing link and the network service carry the family's name, not a product's: one engine serves every app.
The interface version is one whole number for everything an app and the engine say to each other. An app is
built for one number; when the engine's differs the app says which of the two to update and does nothing else
with that engine. Raise it in the change that breaks an app built for the current one.
"""

from __future__ import annotations

INTERFACE_VERSION = 1
PAIRING_SCHEME = "scribe"
SERVICE_TYPE = "_scribe._tcp"
