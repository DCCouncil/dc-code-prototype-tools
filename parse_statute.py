# Convert a DC Council Statute at Large file, for a single statute
# entry, into XML.
#
# python3 make_sal_xml.py A20-003.docx > output/A20-003.xml
# python3 make_sal_xml.py R20-055.docx > output/R20-055.xml
#
# Chome won't normally render an XSLT instruction when loading from a
# file:// URL. To turn off that security restriction, make sure Chrome
# isn't running at all (check if you need to kill it), and then start
# it with this command-line option:
#
# google-chrome --allow-file-access-from-files 

import sys, re, lxml.etree as etree, datetime
from worddoc import open_docx

def make_node(parent, tag, text, **attrs):
  """Make a node in an XML document."""
  n = etree.Element(tag)
  parent.append(n)
  n.text = text
  for k, v in attrs.items():
    if v is None: continue
    if isinstance(v, datetime.datetime):
      v = format_datetime(v)
    elif isinstance(v, (bool, int)):
      v = str(v)
    n.set(k.replace("___", ""), v)
  return n

# Form the output dom.
dom = etree.Element("measure")

# Load the .docx file.
doc = open_docx(sys.argv[1])

# Parse the header.

header_text = []
for sec in doc["header"]:
	for p in sec["paragraphs"]:
		header_text.append(" ".join(run["text"] for run in p["runs"]))
header_text = "\n".join(header_text)

stat_volume, stat_page, law_type, council_period, law_num, eff_date, exp_date = \
	re.match(r"COUNCIL OF THE DISTRICT OF COLUMBIA\s+(\d+) DCSTAT (\d+)\n"
			 r"(D.C. (?:Law|Act|Resolution)) (\d+)-(\d+), "
			 r"effective ([^(]*[^\s(])"
			 r"(?: \(Expiration date ([^(]*)\))?", header_text).groups()

make_node(dom, "statutes-volume", stat_volume)
make_node(dom, "statutes-page", stat_page)
make_node(dom, "council-period", council_period)
make_node(dom, "law-type", law_type)
make_node(dom, "law-number", law_num)
make_node(dom, "effective-date", eff_date) # TODO: Parse date.
if exp_date: make_node(dom, "expiration-date", exp_date) # TODO: Parse date.
notes_node = None
body_node = None
quotation_node = None
last_margin_note = None
indentation_stack = None

# Parse the body.

state = "start"
def do_paragraph(p):
	global dom
	global state
	global notes_node
	global body_node
	global quotation_node
	global last_margin_note
	global indentation_stack

	p_text = " ".join(run["text"] for run in p["runs"])
		
	if state == "start" and p["properties"].get("style") == "MarginNotes":
		for run in p["runs"]:
			m = re.match("Bill (\d+)-(\d+)$", run["text"])
			if m:
				make_node(dom, "bill-number", m.group(2))
				continue

			m = re.match("Act (\d+)-(\d+)$", run["text"])
			if m:
				make_node(dom, "act-number", m.group(2))
				continue

			m = re.match("Proposed Resolution (\d+)-(\d+)$", run["text"])
			if m:
				make_node(dom, "proposed-resolution-number", m.group(2))
				continue

			m = re.match(r"Emergency Declaration Res\. (\d+-\d+)\s*$", run["text"])
			if m:
				make_node(dom, "emergency-declaration", None, resolution=m.group(1))
				state = "em-dec-res-stat"
				continue

			if run["text"] == "effective":
				state = "effective-date"
				break
				
			#print("Unhandled margin note:", run)
			state = "title"
			if notes_node is None:
				notes_node = make_node(dom, "notes", "")
			else:
				notes_node.text += " "
			notes_node.text += " ".join(run["text"] for run in p["runs"])
			
	elif state == "effective-date" and p["properties"].get("style") == "MarginNotes":
		# TODO: Parse date.
		make_node(dom, "act-effective", " ".join(run["text"] for run in p["runs"]))
		state = "title"

	elif state == "em-dec-res-stat" and p["properties"].get("style") == "MarginNotes":
		dom.xpath("emergency-declaration")[0].set("statute", " ".join(run["text"] for run in p["runs"]))
		state = "title"

	elif state == "title" and p["properties"].get("style") == "MarginNotes":
		if notes_node is None:
			notes_node = make_node(dom, "notes", "")
		else:
			notes_node.text += " "
		notes_node.text += " ".join(run["text"] for run in p["runs"])

	elif state == "title" and p["properties"].get("style") == "Longtitle":
		make_node(dom, "long-title", " ".join(run["text"] for run in p["runs"]).strip())
		state = "body"
		
	elif state == "title" and p_text.strip() != "":
		make_node(dom, "act-header", p_text)
		
	elif state == "body":
		if body_node is None:
			body_node = make_node(dom, "body", None)
			indentation_stack = [(None, body_node)]

		if p["properties"].get("frame"):
			if not last_margin_note or last_margin_note[0] != p["properties"]["frame"]:
				if p_text.strip() == "": return
				last_margin_note = (p["properties"]["frame"], etree.Element("margin-notes"))
			make_node(last_margin_note[1], "line", p_text)
				
		elif p_text.strip() != "":
			# Is this inside a quotation?
			if p_text.strip().startswith("“"):
				if not quotation_node:
					# Create a <quotation> node, and save/reset the indentation_stack.
					quotation_node = (make_node(indentation_stack[-1][1], "quotation", None), indentation_stack)
					indentation_stack = [(None, quotation_node[0])]
			elif quotation_node:
				# End whatever quoted region we were in.
				indentation_stack = quotation_node[1]
				quotation_node = None
			
			# Current indentation level.
			indent = p["properties"].get("indentation", 0)
			if p["properties"].get("align") == "center": indent = 0
			
			# If we're at less indentation that we last saw, pop off all entries
			# at a greater or equal indentation level.
			while len(indentation_stack) > 1 and indentation_stack[-1][0] >= indent:
				indentation_stack.pop(-1)
			
			# What node are we going to insert into?
			container = indentation_stack[-1][1]

			# If we saw a margin note, put it right before the following paragraph.
			if last_margin_note:
				container.append(last_margin_note[1])
				last_margin_note = None
				
			# Make a node and put it on the indentation stack.
			para = make_node(container, "para", None)
			indentation_stack.append( (indent, para) )
		
			# Separate list numbering.
			m = re.match("\s*(\([^)]+\))+\s*", p["runs"][0]["text"])
			if m:
				make_node(para, "num", m.group(0).strip())
				p["runs"][0]["text"] = p["runs"][0]["text"][len(m.group(0)):]
			
			# Being smart about "(c)(1)" type numbering is impossible because
			# we don't know if the subsequent indent corresponds to the (1) level
			# or is indentation within that. We need to compare numbering styles.
			#number_node = None
			#while True:
			#	m = re.match("\([^)]+\)\s*", p["runs"][0]["text"])
			#	if not m: break
			#	if number_node is None:
			#		number_node = make_node(para, "num", m.group(0).strip())
			#	else:
			#		para = make_node(para, "para", None)
			#		indentation_stack.append( (indent, para) )
			#		number_node = make_node(para, "num", m.group(0).strip())
			#	p["runs"][0]["text"] = p["runs"][0]["text"][len(m.group(0)):]

			# Add text inside here.
			t = make_node(para, "t", "")
			last_run = None
			for i, run in enumerate(p["runs"]):
				# Strip off quotation marks at the start of quoted text because it
				# is a display thing, not a semantic thing, once we embed the text
				# within a <quotation> node.
				#if quotation_node and i == 0 and run["text"].startswith("“"):
				#	run["text"] = run["text"][1:]
				#	# TODO: What to do with the close quote and (non-quoted) text
				#	# like a period that follows the close quote?
				
				# If this run has no formatting commands, insert the text plainly.
				if len(run["properties"]) == 0:
					# Use 'text' of the parent or 'tail' of the last child in this paragraph?
					if last_run == None:
						t.text += run["text"]
					else:
						last_run.tail = (last_run.tail if last_run.tail else "") + run["text"]
						
				# This run has formatting, so use a <span>.
				else:
					last_run = make_node(t, "span", run["text"], **run["properties"])
			
	elif len(p["runs"]) > 0:
		print("Unhandled paragraph", p)

# Output the document.

for sec in doc["sections"]:
	for p in sec["paragraphs"]:
		do_paragraph(p)

print('<?xml-stylesheet href="statute_to_html.xsl" type="text/xsl"?>') # cheating by not using etree
#print(etree.tostring(dom, pretty_print=True, encoding=str))
sys.stdout.buffer.write(etree.tostring(dom, pretty_print=True, encoding="utf-8"))
