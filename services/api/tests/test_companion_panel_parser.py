"""Unit tests for companion_panel_parser (NG12 1.7.1 weighted checklist)."""

from __future__ import annotations

from bs4 import BeautifulSoup

from app.services.companion_panel_parser import (
    parse_companion_panels_after_article,
    parse_score_threshold,
)

_NG12_171_HTML = """
<div class="section" title="Malignant melanoma of the skin">
  <article id="ng12-1_7_1" class="numbered-paragraph">
    <h5>1.7.1</h5>
    <div>
      <p>Refer people using a suspected cancer pathway referral for melanoma
      if they have a suspicious pigmented skin lesion with a weighted
      7-point checklist score of 3 or more. <strong>[2015]</strong></p>
    </div>
  </article>
  <div class="panel panel--primary" title="Weighted 7-point checklist">
    <h5 class="title">Weighted 7-point checklist</h5>
    <p>Major features of the lesions (scoring 2 points each):</p>
    <div class="itemizedlist">
      <ul class="itemizedlist">
        <li class="listitem"><p>change in size</p></li>
        <li class="listitem"><p>irregular shape</p></li>
        <li class="listitem"><p>irregular colour</p></li>
      </ul>
    </div>
    <p>Minor features of the lesions (scoring 1 point each):</p>
    <div class="itemizedlist">
      <ul class="itemizedlist">
        <li class="listitem"><p>largest diameter 7 mm or more</p></li>
        <li class="listitem"><p>inflammation</p></li>
        <li class="listitem"><p>oozing</p></li>
        <li class="listitem"><p>change in sensation</p></li>
      </ul>
    </div>
  </div>
  <article id="ng12-1_7_2" class="numbered-paragraph">
    <h5>1.7.2</h5>
    <div><p>Refer people if dermoscopy suggests melanoma. [2015]</p></div>
  </article>
</div>
"""


def test_parse_score_threshold():
    assert parse_score_threshold("score of 3 or more") == 3
    assert parse_score_threshold("no score here") is None


def test_parse_weighted_checklist_after_1_7_1():
    soup = BeautifulSoup(_NG12_171_HTML, "html.parser")
    article = soup.find("article", id="ng12-1_7_1")
    assert article is not None
    panels = parse_companion_panels_after_article(
        article,
        article.get_text(" ", strip=True),
    )
    assert len(panels) == 1
    panel = panels[0]
    assert panel["kind"] == "weighted_checklist"
    assert panel["threshold"] == 3
    assert len(panel["groups"]) == 2
    assert panel["groups"][0]["points"] == 2
    assert [i["text"] for i in panel["groups"][0]["items"]] == [
        "change in size",
        "irregular shape",
        "irregular colour",
    ]
    assert panel["groups"][1]["points"] == 1
    assert len(panel["groups"][1]["items"]) == 4


def test_panel_does_not_attach_to_next_article():
    soup = BeautifulSoup(_NG12_171_HTML, "html.parser")
    article = soup.find("article", id="ng12-1_7_2")
    assert article is not None
    panels = parse_companion_panels_after_article(article, "dermoscopy")
    assert panels == []
