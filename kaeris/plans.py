"""The four public plans, as the site states them: a copy of `tools/plans.json` in the site
repository (kaeris-i18n-tool), whose numbers a backend test pins to the server's own limits.

The CLI ships without the site repository and `kaeris check` never touches the network, so the
copy lives here. tests/test_plans_are_the_sites.py compares it with the site's file whenever that
file is reachable (KAERIS_SITE_REPO, or ../i18n_tool beside this repository) and with the README;
npm/src/plans.js is generated from this module by npm/tools/gen_tables.py.

Units are characters, metered the way the server meters a run (kaeris/estimate.py)."""

PLANS = {
    "free":     {"price": 0,  "file": 10000,   "file_with_key": 50000, "month_with_key": 1500000,
                 "day_without_key": 300000, "langs": 8},
    "lifetime": {"price": 79, "file": 1000000, "month": None, "langs": 46, "own_key": True},
    "pro":      {"price": 19, "annual": 190, "file": 100000,  "month": 12000000, "langs": 46},
    "teamapi":  {"price": 79, "annual": 790, "file": 1000000, "month": 60000000, "langs": 46},
}
