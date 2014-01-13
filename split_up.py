# Spits up a <dc-code> master file into many smaller files
# and inserts XIncludes to tie them all together.
#
# Usage:
# python3 split_up.py dest_dir < code.xml

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

def write_node(node, path, filename, backpath, toc):
	# Besides in Sections, move any <level>s into separate files
	# and replace them with XInclude tags.
	if node.xpath("string(type)") not in ("Section", "placeholder"):
		for child in node.xpath("level[not(type='annotations')]"):
			# When we recurse, where should we put the file?

			if child.xpath("string(type)") == "placeholder":
				if child.xpath("string(section)"):
					fn = child.xpath("string(section)") + "~P.xml"
				elif child.xpath("string(section-start)") and child.xpath("string(section-end)"):
					fn = child.xpath("string(section-start)") + "~" + child.xpath("string(section-end)") + "~P.xml"
				else:
					raise Exception()
				sub_path = ""
				bp = backpath
			elif child.xpath("string(type)") == "Section":
				fn = child.xpath("string(num)") + ".xml"
				sub_path = ""
				bp = backpath
			else:
				fn = "index.xml"
				sub_path = child.xpath("string(type)") + "-" + child.xpath("string(num)") + "/"
				if not os.path.exists(sys.argv[1] + path + sub_path): os.mkdir(sys.argv[1] + path + sub_path)
				bp = backpath + "../"

			# Add a TOC entry.
			
			toc_entry = make_node(toc, child.tag, None)
			make_node(toc_entry, "href", path + sub_path + fn)
			for tag in ("type", "num", "section", "section-start", "section-end", "section-range-type", "heading", "reason"):
				if child.xpath("string(%s)" % tag): make_node(toc_entry, tag, child.xpath("string(%s)" % tag))
			if child.xpath("string(type)") not in ("Section", "placeholder"): 
				toc_entry_container = make_node(toc_entry, "children", None)
			else:
				toc_entry_container = None

			# Recurse into this node.

			write_node(child, path + sub_path, fn, bp, toc_entry_container)

			# Replace the node with an XInclude.

			xi = lxml.etree.Element("{http://www.w3.org/2001/XInclude}include")
			xi.set("href", sub_path + fn)
			child.addprevious(xi)
			child.getparent().remove(child)

	# lxml doesn't round-trip CDATA, so put those back.
	for child in node.xpath("//text[@encoding='xhtml']"):
		child.text = lxml.etree.CDATA(child.text)

	# Write the remaining part out to disk.
	with open(sys.argv[1] + path + filename, "wb") as f:
		# lxml.etree.ProcessingInstruction does not work. Write the PI directly.
		f.write(('<?xml-stylesheet href="%srender/%s.xsl" type="text/xsl" ?>\n' % (backpath, "section" if node.xpath("string(type)") in ("Section", "placeholder") else "biglevel")).encode("utf8"))
		f.write(lxml.etree.tostring(node, pretty_print=True, encoding="utf-8", xml_declaration=False))

# Read in the master code file.
dom = lxml.etree.parse(sys.stdin.buffer, lxml.etree.XMLParser(remove_blank_text=True))

# Create an empty TOC DOM.
toc = lxml.etree.Element("toc")

# Write out the split-up XML files.
write_node(dom.getroot(), '/', "index.xml", "", toc)

# Write out the TOC file.
with open(sys.argv[1] + 'toc.xml', "wb") as f:
	f.write(lxml.etree.tostring(toc, pretty_print=True, encoding="utf-8", xml_declaration=False))
