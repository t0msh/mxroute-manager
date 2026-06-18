/** Load shared JS modules onto window before classic app.js runs. */
import * as permissions from "./permissions.js";
import * as utils from "./utils.js";
import * as cache from "./cache.js";

window.Mxm = { permissions, utils, cache };
