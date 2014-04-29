# Spits up a DC Code master file into many smaller files
# and inserts XIncludes to tie them all together.
#
# Usage:
# python3 split_up.py dest_dir < code.xml

import sys, os, os.path, lxml.etree, re

def make_node(parent, tag, text, **attrs):
  """Make a node in an XML document."""
  n = lxml.etree.Element(tag)
  parent.append(n)
  n.text = text
  for k, v in attrs.items():
    if v is None: continue
    n.set(k, v)
  return n

def write_node(node, path, filename, backpath, toc, seen_filenames):
	# Besides in Sections, move any <level>s --- besides Divisions --- into separate files
	# and replace them with XInclude tags. We don't split at Divisions because these are
	# of no interest to anyone, the numbering of titles has global scope, and it just feels
	# like clutter.
	if node.xpath("string(type)") == "document":
		subnodes = node.xpath("level[prefix='Division']/level[prefix='Title']")
	elif node.xpath("string(prefix)") == "Title":
		subnodes = node.xpath("level[(type='toc' or type='section' or type='placeholder') and not(prefix='Subtitle')] | level[prefix='Subtitle']/level[(type='toc' or type='section' or type='placeholder')]")
	elif node.xpath("string(type)") == "toc":
		subnodes = node.xpath("level[(type='toc' or type='section' or type='placeholder')]")
	else:
		subnodes = None

	if subnodes:
		for child in subnodes:
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
			elif child.xpath("string(type)") == "section":
				fn = child.xpath("string(num)") + ".xml"
				sub_path = ""
				bp = backpath
			else:
				fn = "index.xml"
				sub_path = clean_filename(child.xpath("string(prefix)") + "-" + child.xpath("string(num)")) + "/"
				if not os.path.exists(sys.argv[1] + path + sub_path): os.mkdir(sys.argv[1] + path + sub_path)
				bp = backpath + "../"

			# Add a TOC entry.
			
			toc_entry = make_node(toc, child.tag, None)
			make_node(toc_entry, "href", path + sub_path + fn)
			for tag in ("type", "num", "section", "section-start", "section-end", "section-range-type", "heading", "reason"):
				if child.xpath("string(%s)" % tag): make_node(toc_entry, tag, child.xpath("string(%s)" % tag))
			if child.xpath("string(type)") == "toc": 
				toc_entry_container = make_node(toc_entry, "children", None)
			else:
				toc_entry_container = None

			# Recurse into this node.

			write_node(child, path + sub_path, fn, bp, toc_entry_container, seen_filenames)

			# Replace the node with an XInclude.

			xi = lxml.etree.Element("{http://www.w3.org/2001/XInclude}include")
			xi.set("href", sub_path + clean_filename(fn))
			child.addprevious(xi)
			child.getparent().remove(child)

	# Write the remaining part out to disk.

	fn = sys.argv[1] + path + clean_filename(filename)
	if fn in seen_filenames: raise Exception("Sanity check failed. Two parts of the code mapped to the same file name.")
	seen_filenames.add(fn)

	with open(fn, "wb") as f:
		f.write(lxml.etree.tostring(node, pretty_print=True, encoding="utf-8", xml_declaration=False))

def clean_filename(fn):
	return re.sub("[^0-9A-Za-z\-\.\~]+", "_", fn)

# Read in the master code file.
dom = lxml.etree.parse(sys.stdin.buffer, lxml.etree.XMLParser(remove_blank_text=True))

# Create an empty TOC DOM.
toc = lxml.etree.Element("toc")

# Write out the split-up XML files.
write_node(dom.getroot(), '/', "index.xml", "", toc, set())

# Write out the TOC file.
with open(sys.argv[1] + 'toc.xml', "wb") as f:
	f.write(lxml.etree.tostring(toc, pretty_print=True, encoding="utf-8", xml_declaration=False))
