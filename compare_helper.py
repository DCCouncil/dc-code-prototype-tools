# This tool normalizes various parts of the DC Code XML so that
# the XML derived from the 2012 West file and the XML derived from
# the 2013 Lexis file can be compared more easily using diff.
#
# Usage:
# python3 code_file.xml > new_file.xml

import sys, lxml.etree, re

def strnorm(s):
	if s is None: return s
	return re.sub(r"\W", "", s).lower()

dom = lxml.etree.parse(sys.stdin.buffer)

# don't compare annotations, there are too many differences
for n in dom.xpath('//level[type="annotations"]|//formerly-cited-as'):
	n.getparent().remove(n)

for n in dom.xpath('//level'):
	# A level that only contains levels. Bad indentation in the West file.
	#if len(n.xpath('*[not(name(.)="level")]')) == 0:
	#	for c in n:
	#		n.addprevious(c)
	#	n.getparent().remove(n)

	# West and Lexis handled subsection headings differently. We didn't
	# even parse from West. Make West look like Lexis.
	t = n.xpath("text/node()[1][@i='True']")
	if len(t):
		t = t[0]
		p = t.getparent()
		p.addprevious(t)
		p.text = re.sub("^ -- ", "", t.tail) if t.tail is not None else None
		t.text = re.sub("\.$", "", t.text)
		t.tail = "\n"
		t.tag = "heading"
		t.attrib.pop("i")

	# Actually don't even compare within-section hierarchy because there are
	# too many differences. Unfold the levels.
	for c in n:
		n.addprevious(c)
	n.getparent().remove(n)


# normalize text because there are case, punctuation, and whitespace changes
for n in dom.xpath('//heading'):
	n.text = strnorm(n.text)
for n in dom.xpath('//text'):
	n.text = strnorm(n.text)

	# remove empty <text/> from the West file
	if len(n) == 0 and n.text in ("", None):
		n.getparent().remove(n)

# remove placeholder text from Lexis which wasn't in West (usually <text>Repealed</text>)
for n in dom.xpath('//placeholder/text'):
	n.getparent().remove(n)

sys.stdout.buffer.write(lxml.etree.tostring(dom, pretty_print=True, encoding="utf-8", xml_declaration=True))

