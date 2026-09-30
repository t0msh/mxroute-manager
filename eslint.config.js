// Classic browser scripts in static/js/app/ share global scope across files and HTML (see docs/frontend-app-scripts.md).
// Pure ES module helpers under static/js/*.js are linted and covered by unit tests.
export default [
  {
    ignores: ["static/js/app/**"],
  },
];
