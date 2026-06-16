import unittest
from unittest.mock import patch
from xml.etree import ElementTree

import requests

from ai_papers import fetcher


SAMPLE_XML = """<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns='http://www.w3.org/2005/Atom' xmlns:arxiv='http://arxiv.org/schemas/atom'>
  <entry>
    <id>http://arxiv.org/abs/2401.12345v1</id>
    <title>  Test   Paper  </title>
    <summary>  Summary text   here. </summary>
    <author><name>Alice</name></author>
    <author><name>Bob</name></author>
    <arxiv:primary_category term='astro-ph.CO'/>
    <category term='astro-ph.CO'/>
    <category term='astro-ph.GA'/>
    <published>2026-01-01T00:00:00Z</published>
    <link title='pdf' href='http://arxiv.org/pdf/2401.12345v1'/>
  </entry>
</feed>
"""


class _Resp:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


class TestFetcher(unittest.TestCase):
    def setUp(self):
        self.source = fetcher.ArxivSource()

    def test_parse_entry(self):
        root = ElementTree.fromstring(SAMPLE_XML)
        entry = root.find(f"{self.source.ATOM_NS}entry")
        parsed = self.source._parse_entry(entry)

        self.assertEqual(parsed["arxiv_id"], "2401.12345")
        self.assertEqual(parsed["title"], "Test Paper")
        self.assertIn("astro-ph.CO", parsed["categories"])
        self.assertEqual(parsed["authors"], ["Alice", "Bob"])

    @patch("ai_papers.fetcher.time.sleep")
    @patch("ai_papers.fetcher.requests.get")
    def test_fetch_papers_success(self, mock_get, _mock_sleep):
        mock_get.return_value = _Resp(SAMPLE_XML)
        papers = self.source.fetch(["astro-ph.CO"], max_results=1, days_back=1)

        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["arxiv_id"], "2401.12345")

    @patch(
        "ai_papers.fetcher.requests.get", side_effect=requests.RequestException("boom")
    )
    def test_fetch_papers_handles_request_exception(self, _mock_get):
        papers = self.source.fetch(["astro-ph.CO"], max_results=1, days_back=1)
        self.assertEqual(papers, [])

    @patch("ai_papers.fetcher.time.sleep")
    @patch("ai_papers.fetcher.requests.get")
    def test_fetch_papers_simple_builds_category_query(self, mock_get, _mock_sleep):
        mock_get.return_value = _Resp(SAMPLE_XML)

        self.source.fetch_simple(["astro-ph.CO", "astro-ph.GA"], max_results=1)

        _, kwargs = mock_get.call_args
        query = kwargs["params"]["search_query"]
        self.assertIn("cat:astro-ph.CO", query)
        self.assertIn("cat:astro-ph.GA", query)


if __name__ == "__main__":
    unittest.main()
