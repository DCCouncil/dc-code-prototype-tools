# Convert the DC Code .docx file from West into XML.
#
# Usage:
# python3 parse_code_doc.py path/to/dc_code_unofficial_2012-12-11/ > dc_code_unofficial_2012-12-11.xml

import sys, io, glob, re, lxml.etree as etree, datetime, pprint
from worddoc import open_docx

ANNOTATION_HEADINGS = ("CREDIT(S)", "HISTORICAL AND STATUTORY NOTES", "UNIFORM COMMERCIAL CODE COMMENT", "ACKNOWLEDGMENT")

def main():
	# Form the output dom.
	dom = etree.Element("level")
	make_node(dom, "type", "document")
	make_node(dom, "heading", "Code of the District of Columbia")
	meta = make_node(dom, "meta", None)
	make_node(meta, "current-through", "2012-12-11")
	
	# Where did we insert the previous section into the table of contents hierarchy?
	# This is a list of pairs of hierarchy info and the dom node corresponding to
	# that level.
	toc_location_stack = [(None, dom)]
	
	# Parse each title of the code in order.
	for fn in sorted(glob.glob(sys.argv[1] + "/*.docx")):
		titlenum = re.search("/([^/]*)\.docx", fn).group(1)
		print(fn, "...", file=sys.stderr)
		parse_title(fn, dom, toc_location_stack)

	# Output, being careful we get UTF-8 to the byte stream.
	sys.stdout.buffer.write(etree.tostring(dom, pretty_print=True, encoding="utf-8", xml_declaration=True))

def parse_title(fn, dom, toc_location_stack):
	# Load the .docx file.
	doc = open_docx(fn, drawing=drawing_handler)
	
	# Parse each section.
	for section in doc["sections"]:
		parse_section(section, dom, toc_location_stack)
	
def parse_section(section, dom, toc_location_stack):
	# Parse the intro matter of the section, including the table of contents
	# spine pointers, and create a node in the right place in the dom.
	sec_node, remaining_paras = parse_section_intro_matter(section, dom, toc_location_stack)
	if sec_node is None: return
	
	# Remove certain boilerplate text from the end of the section.
	while len(remaining_paras) > 0 and \
		(re.match("\s*Current through December 11, 2012\s*$|END OF DOCUMENT$", para_text_content(remaining_paras[-1]))
			or 
		para_text_content(remaining_paras[-1]) == "DC CODE § " + sec_node.xpath("string(num)")
			):
		remaining_paras.pop(-1)
	
	# Parse the body of the section.
	remaining_paras = parse_section_body(sec_node, remaining_paras)

	# Parse the annotations at the end of the section.
	parse_section_annotations(sec_node, remaining_paras)

def parse_section_intro_matter(section, dom, toc_location_stack):
	global M # utility for doing regular expressions
	
	# Filter out empty paragraphs.

	paras = [p for p in section["paragraphs"] if para_text_content(p) != ""]
	if len(paras) == 0: return None, None
	
	# If the first paragraph is in Courier New, this seems to indicate a continued section,
	# either because this section contains a table or the previous section contains a table.
	# In this case, return the last node we created.

	if len(section["paragraphs"][0]["runs"]) == 1 and section["paragraphs"][0]["runs"][0]["properties"].get("font") == "Courier New":
		return (toc_location_stack[-1][1].xpath("*")[-1], paras)

	# Parse the intro matter of the section.
	
	former_cited_as = []
	toc_location = [None] # first element here (None) matches first element of toc_location_stack (None, dom).
	section_number = None
	section_name = None
	placeholder_info = None
	
	for i, paragraph in enumerate(paras):
		ptext = para_text_content(paragraph)

		if re_match("Formerly cited as (.*)", ptext):
			former_cited_as.append(M.group(1))
		elif re_match("District of Columbia Official Code 2001 Edition Currentness", ptext):
			continue # skip this
		elif re_match("(?:@@DRAWING@@)?\s*(Division|Subdivision|Title|Subtitle|Chapter|Subchapter|Part|Subpart|Unit|Article) ([A-Za-z0-9\-]+)\s?\. (.*\S)\s*", ptext):
			toc_location.append(M.groups())
		elif re_match("(?:@@DRAWING@@)?\s*Appendix", ptext):
			# Title 28 has a part just called "Appendix".
			toc_location.append(("Appendix", None, None))
		elif toc_location[-1] == ('Part', '5', 'Default.') and re_match("(?:@@DRAWING@@)?\s*([A-C])\. (.*\S)\s*", ptext):
			# e.g. 28:2A-502 is in Part 5 and then a subpart numbered A that doesn't say what type of level it is.
			toc_location.append( ("level", M.group(1), M.group(2)) )

		elif re_match("(?:@@DRAWING@@)?\s*§§? (?P<section_start>\S+)(?:(?P<section_range_type> to|,) (?P<section_end>\S+))?\. (?:(?P<title>.*) )?\[(?P<reason>Expired|Repealed|Omitted|Reserved|Renumbered)\]", ptext):
			# A placeholder for an expired/repealed section or range of sections.
			# This has to come before the normal section number/title line regex.
			placeholder_info = M.groupdict()
			break
		elif re_match("(?:@@DRAWING@@)?\s*§§? (?P<section_start>\S+)(?:(?P<section_range_type> to|,) (?P<section_end>\S+))?\. (?P<reason>Expired|Repealed|Omitted|Reserved|Renumbered)", ptext):
			# Aanother form of placeholder
			placeholder_info = M.groupdict()
			break
		elif re_match("(?:@@DRAWING@@)?\s*§ (\d+A?(?::[\d\.A-Za-z]+)?-[\d\.A-Za-z]+). (.*)", ptext):
			# This is the section number and name, and signifies the end of the intro
			# matter of the section.
			section_number, section_title = M.groups()
			break

		elif ptext == "This document has been updated. Use KEYCITE.":
			# No idea what this means, but appears to be something we can skip.
			# It's centered, so it must come before align=center test.
			continue

		elif paragraph["properties"].get("align") == "center":
			# Occurs in document sections that don't appear to be proper sections of the code.
			i -= 1 # include this line in the body
			break
		elif len(paragraph["runs"]) == 1 and paragraph["runs"][0]["properties"].get("font") == "Courier New":
			# Occurs in document sections that don't appear to be proper sections of the code.
			i -= 1 # include this line in the body
			break
		elif re.match("DC CODE D\. .*, (Refs & Annos|Reserved)", ptext):
			# Occurs in document sections that don't appear to be proper sections of the code.
			i -= 1 # include this line in the body
			break
		elif ptext in ANNOTATION_HEADINGS\
			or ptext in ("REPEAL OF UNIFORM ARBITRATION ACT", "TABLE OF DISPOSITION OF SECTIONS IN FORMER ARTICLE 9 AND OTHER CODE SECTIONS", "REVISION OF ARTICLE 9 OF THE UCC"):
			# Occurs in document sections that don't appear to be proper sections of the code.
			i -= 1 # include this line in the body
			break		

		elif re_match("\(((Effective|Approved) .*)\)", ptext):
			# This is metadata, but also the first line of some parts that don't have sections
			# inside them but have content. So we'll end the metadata here.
			i -= 1 # include this line in the body
			break
		elif re_match("<(This .*)>", ptext):
			# e.g. <This subchapter has expired effective October 30, 1999.>
			# This is metadata, but also the first line of some parts that don't have sections
			# inside them but have content. So we'll end the metadata here.
			i -= 1 # include this line in the body
			break

		else:
			raise ValueError("Unhandled section intro line: " + ptext)
	else:
		raise ValueError("Did not find start of section.")
			
	# Did we encouter required elements?
	if len(toc_location) <= 1:
		raise ValueError("No table of contents location.")
		
	paragraphs_consumed = i
			
	# Where should we insert this entry into the dom? Who's its parent?
	
	parent_node = toc_location_stack[0][1]
	for i, (level, level_node) in enumerate(toc_location_stack):
		# If this level matches, move in.
		if level == toc_location[0]:
			parent_node = level_node
			toc_location.pop(0)
			if len(toc_location) == 0: break # no more levels to check
			continue
			
		# The level no longer matches. Pop the stack up to this point.
		for ii in range(i, len(toc_location_stack)):
			toc_location_stack.pop(i)
		break
		
	# We found the parent, but we may have to create new levels.
	for level_type, level_number, level_title in toc_location:
		parent_node = make_node(parent_node, "level", None)
		make_node(parent_node, "type", level_type)
		if level_number: make_node(parent_node, "num", level_number)
		if level_title: make_node(parent_node, "heading", level_title)
		toc_location_stack.append( ((level_type, level_number, level_title), parent_node) )

	# Not all content is contained within a section.
	if section_number:
		# Make the section node.
		sec_node = make_node(parent_node, "level", None)
		make_node(sec_node, "type", "Section")
		make_node(sec_node, "num", section_number)
		make_node(sec_node, "heading", section_title)
	elif placeholder_info:
		sec_node = make_node(parent_node, "placeholder", None)
		make_node(sec_node, "type", placeholder_info["reason"])
		make_node(sec_node, "section-start" if placeholder_info["section_end"] else "section", placeholder_info["section_start"])
		if placeholder_info["section_end"]:
			make_node(sec_node, "section-end", placeholder_info["section_end"])
			make_node(sec_node, "section-range-type", "list" if placeholder_info["section_range_type"] == ",z" else "range")
		if placeholder_info.get("title"): make_node(sec_node, "heading", placeholder_info["title"])
	else:
		# Some parts have content directly within them. We had better not
		# have already put nodes here, besides metadata.
		if parent_node.xpath("*[not(name() = 'type' or name() = 'num' or name() = 'heading')]"):
			raise ValueError("Adding body content to a level that already has body content or subparts.")
		sec_node = make_node(parent_node, "chapeau", None)
	
	for fs in former_cited_as:
		make_node(sec_node, "formerly-cited-as", fs)
		
	# Return node in which to put body content.
		
	return (sec_node, paras[paragraphs_consumed+1:])
			
def parse_section_body(sec_node, paras):
	global M

	if len(paras) == 0:
		return []
	
	# Parse the section content.
	
	indentation_stack = [sec_node]
	
	for i, paragraph in enumerate(paras):
		# Look for a marker that we've moved into annotations.
		if para_text_content(paragraph) in ANNOTATION_HEADINGS:
			return paras[i:]
		
		# Where do we go in the indentation stack? Indentation appears to be exactly
		# in increments of 180, but round just in case.
		# TODO: Sanity check indentation levels.
		indent_level = int(round(paragraph["properties"].get("indentation", 0) / 180.0)) + 1
		while indent_level < len(indentation_stack): indentation_stack.pop(-1)
		while indent_level > len(indentation_stack):
			indentation_stack.append(make_node(indentation_stack[-1], "level", None))
		
		# If the paragraph starts immediately with a number ("(3)" or "(A)" etc.),
		# move that into a separate node. Handle numbering like "(3)(A)".
		# TODO: Does this grab too much??
		is_first_number = True
		while len(paragraph["runs"]) > 0 and re_match("\([0-9A-Za-z\-\.]+\)\s*", paragraph["runs"][0]["text"], dollar_sign=False):
			num = M.group(0)
			if is_first_number:
				p = make_node(indentation_stack[-1], "level", None)
				indentation_stack.append(p)
				make_node(p, "num", num.strip())
				is_first_number = False
			else:
				# This line has two or more numbers together, like "(3)(A)", which
				# represents implicit indentation. Create a new level of indentation.
				p = make_node(indentation_stack[-1], "level", None)
				indentation_stack.append(p)
				make_node(p, "num", num.strip())
				
			r = paragraph["runs"][0]
			r["text"] = r["text"][len(num):] # strip the number we found from the text
			if r["text"] == "": paragraph["runs"].pop(0) # remove run if nothing left

		if is_first_number:
			# This is an un-numbered paragraph. So we'll go straight to a <text> node.
			p = indentation_stack[-1]

		# Append text content.
		t = make_node(p, "text", "") # initialize with empty text content
		runs_to_node(t, paragraph["runs"])
		
	return paras[i+1:]

def parse_section_annotations(sec_node, paras):
	global M
	
	# Parse the section annotations at the end.
	
	if len(paras) == 0: return
	
	annos = make_node(sec_node, "level", None)
	make_node(annos, "type", "annotations")

	heading_levels = [annos]

	def make_heading_level(name):
		n = make_node(heading_levels[-1], "level", None)
		make_node(n, "heading", name)
		return n
	
	for paragraph in paras:
		ptext = para_text_content(paragraph)

		# Top-level heading in all caps.
		if ptext in ANNOTATION_HEADINGS:
			while len(heading_levels) > 1: heading_levels.pop(-1)
			heading_levels.append(make_heading_level(ptext))
			continue

		# Second-level heading in bold.
		if len(paragraph["runs"]) == 1 and paragraph["runs"][0]["properties"].get("b") == True:
			while len(heading_levels) > 2: heading_levels.pop(-1)
			heading_levels.append(make_heading_level(ptext))
			continue

		#if ptext == ptext.upper() and not ptext.startswith("DC CODE "):
		#	print("Is this an annotation heading level?", ptext)

		# Make a node.
		p = make_node(heading_levels[-1], "text", "") # initialize with empty text content
		runs_to_node(p, paragraph["runs"])

def runs_to_node(node, runs):
	# Appending text inside a mixed-content node is a bit complicated with lxml.
	for r in runs:
		# Remove default properties.
		if r["properties"].get("font") == "Times New Roman":
			del r["properties"]["font"]
		elif r["properties"].get("font") == "Courier New":
			r["properties"]["font"] = "monospace"
		else:
			raise ValueError("Unrecognized font: " + r["properties"]["font"])

		# Clean NBSPs
		r["text"] = re.sub("[\u00A0 ]+", " ", r["text"])

		if len(r["properties"]) == 0:
			# No attributes. Append bare text.
			if len(node) == 0:
				# No mixed content in the node yet, so append to text content directly.
				node.text += r["text"]
			else:
				# Parent has mixed content, so we must append text to the last node's tail.
				if node[-1].tail == None: node[-1].tail = ""
				node[-1].tail += r["text"]
		else:
			# This run has attributes. Encode that somehow.
			rn = make_node(node, "text", r["text"])
			for k, v in r["properties"].items(): rn.set(k, repr(v))

def para_text_content(p):
	return "".join(r["text"] for r in p["runs"]).strip()
	
M = None
def re_match(pattern, string, dollar_sign=True):
	# This is a helper utility that returns the match value
	# but also stores it in a global variable so we can still
	# get it.
	global M
	M = re.match(pattern + ("$" if dollar_sign else ""), string)
	return M

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

def drawing_handler(node):
	return "@@DRAWING@@"

main()

