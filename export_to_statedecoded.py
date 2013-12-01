# Exports a big code file into the State Decoded XML format (one section per file).
#
# Usage:
# python3 export_to_statedecoded.py ~/data/dc_code/state_decoded < ~/data/dc_code/2013-10.xml

import sys, os, os.path, lxml.etree

def make_node(parent, tag, text, **attrs):
  """Make a node in an XML document."""
  n = lxml.etree.Element(tag)
  parent.append(n)
  n.text = text
  for k, v in attrs.items():
    if v is None: continue
    n.set(k, v)
  return n

def append_text(node, text):
	# text versus tail
	if len(node) > 0:
		node[-1].tail += "\n\n"
		node[-1].tail += text
	else:
		if node.text != "": node.text += "\n\n"
		node.text += text

def write_section(node, spine, index):
	# Construct a file name,
	if node.xpath("string(type)") == "placeholder":
		if node.xpath("string(section)"):
			name = node.xpath("string(section)")
			fn = name + "~P"
		elif node.xpath("string(section-start)") and node.xpath("string(section-end)"):
			name = node.xpath("string(section-start)") \
			 + (" to " if node.xpath("string(section-range-type)") == "range" else ", ") \
			 + node.xpath("string(section-end)")
			fn = node.xpath("string(section-start)") + "~" + node.xpath("string(section-end)") + "~"
		else:
			raise Exception()
	elif node.xpath("string(type)") == "Section":
		name = node.xpath("string(num)")
		fn = name

	# Construct a StateDecoded-format file.

	dom = lxml.etree.Element("law")

	# structure & units
	struc = make_node(dom, "structure", None)
	for heading, attrs in spine:
		make_node(struc, "unit", heading, **attrs)

	# number, heading, ordering
	make_node(dom, "section_number", name)
	if node.xpath("string(heading)"): make_node(dom, "catch_line", node.xpath("string(heading)"))
	make_node(dom, "order_by", str(index).zfill(10))

	# body content
	body_content = make_node(dom, "text", "")
	render_body(node, body_content, with_heading=False)

	# annotation content
	history_content = make_node(dom, "history", "")
	for n in node:
		if n.xpath("string(type)") == "annotations":
			render_body(n, history_content)
			break

	# Write the remaining part out to disk, ensuring it is utf-8 encoded.
	with open(sys.argv[1] + "/" + fn + ".xml", "wb") as f:
		f.write(lxml.etree.tostring(dom, pretty_print=True, encoding="utf-8", xml_declaration=False))

def traverse_tree(node, spine, index):
	if node.xpath("string(type)") in ("Section", "placeholder"):
		write_section(node, spine, index)
		return

	if node.tag == "level": # not the dc-code root element
		spine = spine + [
			(
				node.xpath("string(heading)"),
				{
					"label": node.xpath("string(type)"),
					"identifier": node.xpath("string(num)"),
					"order_by": str(index).zfill(10),
					"level": str(len(spine)+1),
				}
			)
		]

	for i, child in enumerate(node.xpath("level")):
		traverse_tree(child, spine, i)

def render_body(node, dom, with_heading=True):
	# If there is a heading, no number, and multiple text paragraphs, don't do an inline heading.
	if node.xpath("string(heading)") and not node.xpath("string(num)") and len(node.xpath("text")) > 1:
		append_text(dom, " -- " + node.xpath("string(heading)") + " -- ")
		with_heading = False

	for i, child in enumerate(n for n in node if n.tag in ("text", "level")):
		if child.tag == "text":
			# ignore <span>s that give styled text by just rendering the text content of the node
			# and except if this is the top Section-level, put the level's heading inside the first
			# text paragraph. (The number is handled by the level above because it goes in an attribute.)
			append_text(dom, ""
				+ ((node.xpath("string(heading)") + " -- ") if i == 0 and node.xpath("string(heading)") and with_heading  else "")
				+ lxml.etree.tostring(child, method='text', encoding=str))
		elif child.tag == "level":
			# if the node has a heading but the first child is not text, put the heading in now
			if i == 0 and node.xpath("string(heading)") and with_heading:
				append_text(dom, node.xpath("string(heading)"))

			append_text(dom, "") # force paragraph-like whitespace above the new node
			lvl = make_node(dom, "structure", "")
			lvl.tail = ""

			typ = child.xpath("string(type)")
			if typ in ("form", "table"):
				lvl.set("type", "table")
			elif typ in ("annotations",):
				continue # handled separately
			elif typ in ("Section", "placeholder"):
				pass # nothing special for the top-level node
			elif typ == "":
				# paragraphs
				if child.xpath("string(num)"): lvl.set("prefix", child.xpath("string(num)"))
			elif typ == "appendices":
				pass # no special handling!! TODO
			else:
				raise ValueError(typ)

			if len(child.xpath("text|level")) == 0:
				# if there is nothing inside this level, better put the heading in now
				append_text(lvl, child.xpath("string(heading)"))

			render_body(child, lvl)


# Read in the master code file.
dom = lxml.etree.parse(sys.stdin.buffer, lxml.etree.XMLParser(remove_blank_text=True))

# Write out the split-up XML files.
traverse_tree(dom.getroot(), [], 0)
