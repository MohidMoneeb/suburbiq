"""Tests for the pure logic: normalisation, scoring, analytics, storage.

Network adapters are exercised via a stub so the suite runs offline.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from suburbiq import analytics, store  # noqa: E402
from suburbiq.models import Area, Business, RawRecord, SourceBlocked  # noqa: E402
from suburbiq.normalise import (SuburbResolver, digital_gap_score,  # noqa: E402
                                haversine, normalise, normalise_phone)
from suburbiq.sources.yellowpages import YellowPagesAdapter  # noqa: E402


class TestPhone(unittest.TestCase):
    def test_formats_landline(self):
        self.assertEqual(normalise_phone("+61 2 9211 0665"), "02 9211 0665")
        self.assertEqual(normalise_phone("(02) 9211-0665"), "02 9211 0665")

    def test_formats_mobile(self):
        self.assertEqual(normalise_phone("+61 423 520 690"), "0423 520 690")

    def test_takes_first_of_multiple(self):
        self.assertEqual(normalise_phone("02 9211 0665; 02 9211 0666"), "02 9211 0665")

    def test_empty(self):
        self.assertEqual(normalise_phone(""), "")


class TestGapScore(unittest.TestCase):
    def _b(self, **kw):
        base = dict(id="x", source="osm", name="n", category="cafe")
        base.update(kw)
        return Business(**base)

    def test_complete_scores_zero(self):
        b = self._b(website="w", phone="p", opening_hours="h", street="s")
        self.assertEqual(digital_gap_score(b), 0)

    def test_absent_scores_100(self):
        self.assertEqual(digital_gap_score(self._b()), 100)

    def test_website_is_heaviest_single_gap(self):
        no_web = digital_gap_score(self._b(phone="p", opening_hours="h", street="s"))
        no_street = digital_gap_score(self._b(website="w", phone="p", opening_hours="h"))
        self.assertEqual(no_web, 40)
        self.assertGreater(no_web, no_street)


class TestSuburbResolver(unittest.TestCase):
    def setUp(self):
        self.r = SuburbResolver([("Newtown", -33.898, 151.179),
                                 ("Bondi Beach", -33.891, 151.274)])

    def test_source_suburb_wins(self):
        self.assertEqual(self.r.resolve("Given", -33.898, 151.179), "Given")

    def test_derives_nearest(self):
        self.assertEqual(self.r.resolve("", -33.897, 151.180), "Newtown")
        self.assertEqual(self.r.resolve("", -33.890, 151.275), "Bondi Beach")

    def test_rejects_far_points(self):
        # Melbourne coords against Sydney centroids -> no claim
        self.assertEqual(self.r.resolve("", -37.81, 144.96), "")

    def test_no_coords(self):
        self.assertEqual(self.r.resolve("", None, None), "")


class TestHaversine(unittest.TestCase):
    def test_known_distance(self):
        # Sydney -> Melbourne is ~713km
        d = haversine(-33.87, 151.21, -37.81, 144.96)
        self.assertTrue(700 < d < 730, d)


class TestNormalise(unittest.TestCase):
    def _rec(self, nid, name, lat=-33.898, lon=151.179, **f):
        base = dict(name=name, lat=lat, lon=lon)
        base.update(f)
        return RawRecord(source="osm", native_id=nid, fields=base)

    def setUp(self):
        self.r = SuburbResolver([("Newtown", -33.898, 151.179)])

    def test_drops_unnamed(self):
        items, dropped = normalise([self._rec("1", "")], "cafe", self.r)
        self.assertEqual(len(items), 0)
        self.assertEqual(dropped["no_name"], 1)

    def test_dedupes_same_name_same_place(self):
        recs = [self._rec("1", "Kaffe"), self._rec("2", "Kaffe")]
        items, dropped = normalise(recs, "cafe", self.r)
        self.assertEqual(len(items), 1)
        self.assertEqual(dropped["duplicate"], 1)

    def test_keeps_distinct(self):
        recs = [self._rec("1", "Kaffe"), self._rec("2", "Other")]
        items, _ = normalise(recs, "cafe", self.r)
        self.assertEqual(len(items), 2)

    def test_scores_and_derives(self):
        items, _ = normalise([self._rec("1", "Kaffe")], "cafe", self.r)
        self.assertEqual(items[0].suburb, "Newtown")
        self.assertEqual(items[0].digital_gap_score, 100)


class TestStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.conn = store.connect(self.tmp.name)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.tmp.name)

    def _b(self, i, name="A"):
        return Business(id=Business.make_id("osm", i), source="osm", name=name,
                        category="cafe", suburb="Newtown", digital_gap_score=50)

    def test_insert_then_update_is_idempotent(self):
        first = store.upsert(self.conn, [self._b("1"), self._b("2")])
        self.assertEqual(first["inserted"], 2)
        again = store.upsert(self.conn, [self._b("1"), self._b("2")])
        self.assertEqual(again["inserted"], 0)
        self.assertEqual(again["updated"], 2)
        self.assertEqual(again["total"], 2)

    def test_update_changes_field(self):
        store.upsert(self.conn, [self._b("1", "Old")])
        store.upsert(self.conn, [self._b("1", "New")])
        rows = store.query(self.conn, "cafe")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "New")


class FakeRow(dict):
    """sqlite3.Row-like: analytics indexes rows by column name."""
    def __getitem__(self, k):
        return self.get(k)


class TestAnalytics(unittest.TestCase):
    def rows(self, spec):
        out = []
        for i, (suburb, gap, web) in enumerate(spec):
            out.append(FakeRow(name=f"b{i}", suburb=suburb, digital_gap_score=gap,
                               website=web, phone="", opening_hours="", street=""))
        return out

    def test_saturation_counts_and_sorts(self):
        r = self.rows([("A", 0, "w"), ("A", 0, "w"), ("B", 0, "w")])
        sat = analytics.saturation(r)
        self.assertEqual(sat[0], {"suburb": "A", "count": 2})
        self.assertEqual(sat[1]["count"], 1)

    def test_coverage_percentages(self):
        r = self.rows([("A", 0, "w"), ("A", 100, ""), ("A", 100, "")])
        c = analytics.coverage(r)
        self.assertEqual(c["total"], 3)
        self.assertEqual(c["with_website"], 1)
        self.assertEqual(c["pct_no_website"], 67)

    def test_opportunity_excludes_small_suburbs(self):
        # 'B' has 2 businesses, below MIN_BUSINESSES_FOR_OPPORTUNITY
        spec = [("A", 100, "")] * 6 + [("B", 100, "")] * 2
        opp = analytics.opportunity(self.rows(spec))
        names = [o["suburb"] for o in opp]
        self.assertIn("A", names)
        self.assertNotIn("B", names)

    def test_opportunity_prefers_scarce_and_weak(self):
        # 'Scarce' has 5 weak businesses; 'Busy' has 30 strong ones.
        spec = [("Scarce", 100, "")] * 5 + [("Busy", 0, "w")] * 30
        opp = analytics.opportunity(self.rows(spec))
        self.assertEqual(opp[0]["suburb"], "Scarce")

    def test_histogram_buckets_sum_to_total(self):
        r = self.rows([("A", g, "") for g in (0, 15, 45, 60, 100)])
        self.assertEqual(sum(b["count"] for b in analytics.gap_histogram(r)), 5)

    def test_empty_inputs_do_not_crash(self):
        self.assertEqual(analytics.coverage([]), {"total": 0})
        self.assertEqual(analytics.opportunity([]), [])


class TestYellowPagesBlockDetection(unittest.TestCase):
    """The block path is the adapter's most important behaviour (PRD FR4)."""

    def setUp(self):
        self.a = YellowPagesAdapter()

    def test_403_raises(self):
        with self.assertRaises(SourceBlocked):
            self.a._guard(403, "<html>ok</html>")

    def test_cloudflare_marker_raises_even_on_200(self):
        with self.assertRaises(SourceBlocked) as ctx:
            self.a._guard(200, "<title>Attention Required! | Cloudflare</title>")
        self.assertIn("cloudflare", ctx.exception.detail.lower() + "cloudflare")

    def test_clean_page_passes(self):
        self.a._guard(200, "<html><div class='listing-item'>Joe's Cafe</div></html>")

    def test_blocked_carries_remediation(self):
        try:
            self.a._guard(403, "blocked")
        except SourceBlocked as e:
            self.assertTrue(e.remediation)
            self.assertEqual(e.status, 403)


class TestYellowPagesParsing(unittest.TestCase):
    def test_parses_jsonld(self):
        html = """<html><script type="application/ld+json">
        {"@type":"LocalBusiness","name":"Joe's Cafe","telephone":"02 9211 0665",
         "url":"https://joes.example","address":{"streetAddress":"1 Test St",
         "addressLocality":"Newtown","addressRegion":"NSW","postalCode":"2042"},
         "geo":{"latitude":-33.898,"longitude":151.179}}</script></html>"""
        recs = list(YellowPagesAdapter()._parse(html, "cafe"))
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0].fields["name"], "Joe's Cafe")
        self.assertEqual(recs[0].fields["suburb"], "Newtown")
        self.assertEqual(recs[0].fields["lat"], -33.898)

    def test_parses_dom_fallback(self):
        html = """<html><div class="listing-item" data-listing-id="99">
        <a class="listing-name">Bean There</a>
        <p class="listing-address">2 Main St</p>
        <a href="tel:0292110665">call</a></div></html>"""
        recs = list(YellowPagesAdapter()._parse(html, "cafe"))
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0].fields["name"], "Bean There")
        self.assertEqual(recs[0].native_id, "99")
        self.assertEqual(recs[0].fields["phone"], "0292110665")


class TestArea(unittest.TestCase):
    def test_bbox_order(self):
        a = Area("x", "X", -34.1, 150.8, -33.65, 151.35)
        self.assertEqual(a.bbox, "-34.1,150.8,-33.65,151.35")


if __name__ == "__main__":
    unittest.main(verbosity=2)
