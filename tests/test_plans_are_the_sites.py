"""kaeris/plans.py is a copy of the site's tools/plans.json (kaeris-i18n-tool), whose numbers a
backend test pins to the server's limits. The copy must not drift from it, nor from the README.

The site repository is found at KAERIS_SITE_REPO or ../i18n_tool next to this repository; a
checkout without it (CI of this repo, a user) skips that part and still checks the README."""
import json
import os
import re
import unittest

from kaeris.plans import PLANS

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _site_plans():
    for repo in (os.environ.get("KAERIS_SITE_REPO"),
                 os.path.join(os.path.dirname(ROOT), "i18n_tool")):
        if repo:
            p = os.path.join(repo, "tools", "plans.json")
            if os.path.isfile(p):
                with open(p, encoding="utf-8") as f:
                    return json.load(f)["plans"]
    return None


class PlansAreTheSites(unittest.TestCase):
    def test_same_as_the_sites_plans_json(self):
        site = _site_plans()
        if site is None:
            self.skipTest("the site repository is not here (set KAERIS_SITE_REPO)")
        self.assertEqual(PLANS, site)

    def test_the_readme_states_the_same_prices(self):
        text = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
        m = re.search(r"Pro \$(\d+)/month with (\d+)M characters, Team/API \$(\d+)/month with "
                      r"(\d+)M characters, Lifetime \$(\d+) once", text)
        self.assertIsNotNone(m, "the README's plan sentence changed: update this test with it")
        pro, pro_m, team, team_m, life = map(int, m.groups())
        self.assertEqual(pro, PLANS["pro"]["price"])
        self.assertEqual(pro_m * 1_000_000, PLANS["pro"]["month"])
        self.assertEqual(team, PLANS["teamapi"]["price"])
        self.assertEqual(team_m * 1_000_000, PLANS["teamapi"]["month"])
        self.assertEqual(life, PLANS["lifetime"]["price"])


if __name__ == "__main__":
    unittest.main()
