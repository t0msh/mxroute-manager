"""Optional git/build metadata for the UI version label.

Populate BUILD_SHA, BUILD_BRANCH, and BUILD_DESCRIBE before packaging or deploying
if you want the sidebar/login to show e.g. v0.9.2 · dev@47d575a. Left empty for
local development and plain releases.
"""

BUILD_SHA = ""
BUILD_BRANCH = ""
BUILD_DESCRIBE = ""
