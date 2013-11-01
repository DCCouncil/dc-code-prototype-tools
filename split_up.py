# Spits up a <dc-code> master file into many smaller files
# and inserts XIncludes to tie them all together.
#
# python3 split_up.py dest_dir < code.xml

import sys, os, os.path, lxml.etree

def write_node(node, path, filename, backpath):
	# Besides in Sections, move any <level>s into separate files
	# and replace them with XInclude tags.
	if node.xpath("string(type)") != "Section":
		for child in node.xpath("level[type and num]"):
			# Replace this node with an xinclude.

			if child.xpath("string(type)") != "Section":
				fn = "index.xml"
				sub_path = child.xpath("string(type)") + "-" + child.xpath("string(num)") + "/"
				if not os.path.exists(path + sub_path): os.mkdir(path + sub_path)
				bp = backpath + "../"
			else:
				fn = child.xpath("string(num)") + ".xml"
				sub_path = ""
				bp = backpath

			write_node(child, path + sub_path, fn, bp)

			xi = lxml.etree.Element("{http://www.w3.org/2001/XInclude}include")
			xi.set("href", sub_path + fn)
			child.addprevious(xi)
			child.getparent().remove(child)

	# Write the remaining part out to disk.
	with open(path + filename, "wb") as f:
		# lxml.etree.ProcessingInstruction does not work. Write the PI directly.
		f.write(('<?xml-stylesheet href="%srender/%s.xsl" type="text/xsl" ?>\n' % (backpath, "section" if node.xpath("string(type)") == "Section" else "biglevel")).encode("utf8"))
		f.write(lxml.etree.tostring(node, pretty_print=True, encoding="utf-8", xml_declaration=False))

dom = lxml.etree.parse(sys.stdin.buffer, lxml.etree.XMLParser(remove_blank_text=True))
write_node(dom.getroot(), sys.argv[1]+'/', "index.xml", "")
