# Attribution

This renderer follows the HTML-to-PptxGenJS architecture used by DeepPresenter
(`icip-cas/PPTAgent`, MIT License). The MVP implementation is intentionally smaller:
Playwright extracts computed DOM geometry in Python and this directory renders that
constrained intermediate model with PptxGenJS.

