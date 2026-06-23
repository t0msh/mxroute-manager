/** Load shared JS modules onto window before classic app chunks run. */
import * as permissions from "./permissions.js";
import * as utils from "./utils.js";
import * as cache from "./cache.js";
import * as icons from "./icons.js";
import * as themes from "./themes.js";

window.Mxm = { permissions, utils, cache, icons, themes };
