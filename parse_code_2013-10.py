# Convert the DC Code .docx file from Lexis into XML.
#
# Usage:
# python3 parse_code_2013-10.py path/to/2013-10.docx

import sys, re, lxml.etree as etree, os.path, json
from worddoc import open_docx

heading_case_fix = { }

def main():
	# Use the West XML to get headings in titlecase. The Lexis document has
	# big level headings in all caps.
	west_dom = etree.parse(open("/home/user/data/dc_code/2012-12-11.xml", "rb"))
	for h in west_dom.xpath('//heading'):
		t = h.text.replace(" (Refs & Annos)", "")
		t = re.sub("[\s\.]+$", "", t)
		heading_case_fix[t.upper()] = t

	# Form the output DOM.
	dom = etree.Element("dc-code")
	meta = make_node(dom, "meta", None)
	make_node(meta, "title", "Code of the District of Columbia")
	make_node(meta, "recency", "current through DC Act 19-658; unofficial through D.C. Act 19-682")
	
	# Open the Word file. Use a cached json file if it exists
	# since that's faster that opening the raw .docx file.
	if not os.path.exists("/tmp/doc.cache.json"):
		doc = open_docx(sys.argv[1], pict=pict_handler)
		with open("/tmp/doc.cache.json", "w") as doccache:
			json.dump(doc, doccache, indent=2)
	else:
		doc = json.load(open("/tmp/doc.cache.json"))
	
	try:
		# Parse each section.
		state = { "stack": None }
		for section in doc["sections"]:
			parse_doc_section(section, dom, state)
	except:
		import traceback
		traceback.print_exc()

	# Output, being careful we get UTF-8 to the byte stream.
	sys.stdout.buffer.write(etree.tostring(dom, pretty_print=True, encoding="utf-8", xml_declaration=True))

def pict_handler(node):
	return "@@PICT@@"

def parse_doc_section(section, dom, state):
	# Parses the Word document, one "section" at a time. By section I mean the things
	# between 'section breaks' in Word. Not code sections.

	sec = None
	annos = None
	anno_levels = None

	for para_index, para in enumerate(section["paragraphs"]):
		psty = para["properties"].get("style")
		if psty in ("sepline",): continue

		ptext = para_text_content(para)
		if ptext.strip() == "": continue

		# Skip everything until the first Division of the Code. There
		# are some divisions before that for constitution things.
		if state["stack"] == None:
			if para["properties"].get("style") != "Division" or not ptext.startswith("DIVISION I"):
				continue
			state["stack"] = [(None, dom)]

		# Correct mistakes in the document.
		context_path = "/".join([n[0] + ":" + n[1].xpath("string(num)") for n in state["stack"][1:]])
		if psty == "sectextc" and ptext in ("PART D-i", "PART A", "PART F-i"):
			# This problem occurs more than once. Oddly specific to "PART D-i".
			psty = "Part"
			ptext += "\n" + para_text_content(section["paragraphs"][para_index+2])
			section["paragraphs"][para_index+2]["runs"] = [] # prevent processing later
		elif psty == "sectextc" and re_match("SUBPART \d+A?", ptext):
			psty = "Subpart"
			ptext += "\n" + para_text_content(section["paragraphs"][para_index+2])
			section["paragraphs"][para_index+2]["runs"] = [] # prevent processing later
		elif psty == "sectextc" and re_match("CHAPTER 31A1", ptext):
			psty = "Chapter"
			ptext += "\n" + para_text_content(section["paragraphs"][para_index+1])
			section["paragraphs"][para_index+1]["runs"] = [] # prevent processing later

		elif psty == "sectextc" and re_match("SUBCHAPTER II-A|BLOOMINGDALE AND LEDROIT PARK BACKWATER VALVES", ptext):
			continue # repeated/weird text
		elif psty == "sectextc" and context_path == "Division:V/Title:32/Chapter:13/Subchapter:I" and ptext in ("SUBCHAPTER I", "GENERAL"):
			continue # repeated/weird text

		elif psty == "Section" and re_match(r"(§ 1-15-\d+\.) \n\n([(\[].*)", ptext):
			# 1-15-1. \n\n(21 DCR 3198; 22 DCR 961....
			ptext = M.group(1)

			# move the rest into the next paragraph
			section["paragraphs"][para_index+1]["properties"]["style"] = "sectext" # make sure it shows up
			section["paragraphs"][para_index+1]["runs"].insert(0, {"text": M.group(2) + "\n", "properties": {}})

		elif psty == "sectext" and re_match("§ [\d\-\.]+\s*-\s*(Appendices to §.*)", ptext):
			# move out of annotations and into an appendices level
			if sec is not None: do_paragraph_indentation(sec)
			sec = make_node(sec, "level", None)
			make_node(sec, "type", "appendices")
			make_node(sec, "heading", M.group(1))
			annos = None

		elif ptext == '(1) A notification of disposition must provide the following information:':
			psty = "sectext" # is Section

		elif ptext.strip() in ("(A)", "(B)") and context_path == "Division:V/Title:29/Chapter:8/Subchapter:IV":
			psty = "analysis"
		elif ptext.strip() in ("(a)", "(b)", "(c)", "(d)", "(1)", "(2)") and context_path == "Division:V/Title:29/Chapter:8/Subchapter:X":
			psty = "analysis"

		elif sec is None and ptext.strip() == "Repealed.":
			psty = "annotations"

		#print(psty, ptext)

		if psty in ("sectext", "sectextc", "form", "formc", "table", "tablec", "PlainText"):
			# "form" appears in §1-204.63.

			if sec is None: raise Exception("Not in a section. %s / %s" % (repr(ptext), context_path))
			if annos is not None: raise Exception("Inside annotations.")

			# Parse paragraph numbering.: If the paragraph starts immediately with a number
			# ("(3)" or "(A)" or a sequence of such numbers) move that into a separate node.
			# Handle numbering like "(3)(A)" by splitting them into multiple nodes. Since the
			# document doesn't encode indentation, we will come back later to nest levels.
			# Also support "1. " numbering, which occurs in the reorg plan sections. Mostly
			# because those also have headings, and it's nicer to parse those headings than
			# to leave them as italic spans.
			is_para_level = False
			parent_node = sec
			while len(para["runs"]) > 0 and re_match("\([0-9A-Za-z\-\.]+\)\s*|[0-9a-z\-]+\.\s+", para["runs"][0]["text"], dollar_sign=False, case_sensitive=True):
				num = M.group(0)
				parent_node = make_node(sec, "level", None)
				make_node(parent_node, "num", num.strip())
				is_para_level = True

				# strip the number we found from the text
				r = para["runs"][0]
				r["text"] = r["text"][len(num):]
				if r["text"] == "": para["runs"].pop(0) # remove run if nothing left

			# Parse italic text at the beginning which is the paragraph's header text.'
			if is_para_level and len(para["runs"]) > 0 and para["runs"][0]["properties"].get("i") == True:
				t = para["runs"][0]["text"]
				t = re.sub("\.?\s*$", "", t) # remove trailing period and whitespace
				make_node(parent_node, "heading", t)
				para["runs"].pop(0) # remove it

			# Make a node for the text in the last numbered-paragraph-level we created.
			if len(para["runs"]) > 0:
				t = make_node(parent_node, "text", "") # initialize with empty text content
				if psty not in ("sectext", "sectextc"): t.set("class", psty)
				runs_to_node(t, para["runs"])

		elif psty in ("annotations", "annotationsc", "history"):
			parent_node = sec
			if sec is None:
				if context_path in (
					"Division:I/Title:8/Subtitle:E/Chapter:21A/Subchapter:II",
					"Division:VI/Title:38/Subtitle:III/Chapter:16"):
					# allow annotations outside of a section
					parent_node = state["stack"][-1][1]
				else:
					raise Exception("Not in a section.")

			if annos is None:
				annos = make_node(parent_node, "level", None)
				make_node(annos, "type", "annotations")
				anno_levels = [(None, annos)]

			if psty == "history":
				level_type = "History"
			elif len(para["runs"]) > 0 and para["runs"][0]["properties"].get("b") == True:
				# initial bold text is an annotation level heading
				level_type = ""
				while len(para["runs"]) > 0 and para["runs"][0]["properties"].get("b") == True:
					level_type += para["runs"][0]["text"]
					para["runs"].pop(0)
				level_type = re.sub("[\.\s]*$", "", level_type) # remove the period and space at the end
				if len(para["runs"]) > 0: para["runs"][0]["text"] = re.sub("^\s*", "", para["runs"][0]["text"]) # remove initial space at the start of the text
			else:
				level_type = None

			if level_type and anno_levels[-1][0] != level_type:
				anno_levels = anno_levels[0:1]
				n = make_node(anno_levels[-1][1], "level", None)
				if level_type is not None: make_node(n, "heading", level_type)
				anno_levels.append((level_type, n))
			
			t = make_node(anno_levels[-1][1], "text", "") # initialize with empty text content
			runs_to_node(t, para["runs"])


		elif psty == "Section":
			placeholder_types = "\s*\[(?P<type>Reserved|Expired|Omitted|Transferred|Repealed|Not funded)\]\.?"

			if re_match("§§? (?P<section_start>\S+)(?:(?P<section_range_type> to|,) (?P<section_end>\S*[^\.]))\.? (?P<title>.+?)(?:" + placeholder_types + ")?", ptext):
				# A placeholder for an expired/repealed section or range of sections.
				# This has to come before the normal section number/title line regex.
				if sec is not None: do_paragraph_indentation(sec)
				sec = make_node(state["stack"][-1][1], "level", None)
				make_node(sec, "type", "placeholder")
				if M.groupdict()["type"]: make_node(sec, "reason", M.groupdict()["type"])
				make_node(sec, "section-start" if M.groupdict()["section_end"] else "section", M.groupdict()["section_start"])
				if M.groupdict()["section_end"]:
					make_node(sec, "section-end", M.groupdict()["section_end"])
					make_node(sec, "section-range-type", "list" if M.groupdict()["section_range_type"] == "," else "range")
				if M.groupdict().get("title"): make_node(sec, "heading", M.groupdict()["title"])
				annos = None
				continue
			elif re_match("§§? (?P<section_start>\S*[^\.])\.? (?P<title>.*\S|)" + placeholder_types, ptext):
				# A placeholder for an expired/repealed section or range of sections.
				# This has to come before the normal section number/title line regex.
				if sec is not None: do_paragraph_indentation(sec)
				sec = make_node(state["stack"][-1][1], "level", None)
				make_node(sec, "type", "placeholder")
				make_node(sec, "reason", M.groupdict()["type"])
				make_node(sec, "section", M.groupdict()["section_start"])
				if M.groupdict().get("title"): make_node(sec, "heading", M.groupdict()["title"])
				annos = None
				continue

			elif re_match("§ (\d+A?(?::[\d\.A-Za-z]+)?-[\d\.\-A-Za-z]*[\d\-A-Za-z]).(?:\s*(.*))?", ptext):
				section_number, section_title = M.groups()

			else:
				print(context_path, file=sys.stderr)
				raise Exception("Invalid section line: " + repr(ptext))

			if sec is not None: do_paragraph_indentation(sec)
			sec = make_node(state["stack"][-1][1], "level", None)
			make_node(sec, "type", "Section")
			make_node(sec, "num", section_number)
			make_node(sec, "heading", section_title)

			annos = None

		elif sec is None and psty in ("analysis", "analysisc"):
			# seems to be the table of contents at the start of each level
			# ("...c" styles are for a continued line represented as a new paragraph)
			pass

		elif psty == None:
			pass # ?

		else:
			if re_match("(Division|Subdivision|Title|Subtitle|Chapter|Subchapter|Part|Subpart|Unit|Article)s ([A-Za-z0-9\-]+) (\[Reserved\])", ptext):
				pass
			elif re_match("(Chapter) (11)()", ptext):
				pass
			elif not re_match("(Division|Subdivision|Title|Subtitle|Chapter|Subchapter|Part|Subpart|Unit|Article) ([A-Za-z0-9\-]+)\n([\w\W]*)", ptext):
				raise ValueError("Invalid %s level header: %s" % (psty, ptext))

			level_type, level_number, level_title = M.groups()
			level_title = re.sub("\s+", " ", level_title) # newlines
			level_title = re.sub("[\s\.]+$", "", level_title) # trailing spaces and periods

			# Correct case.
			level_title = heading_case_fix.get(level_title, level_title)

			# This is a TOC level. If the level exists on the TOC stack,
			# pop to that level. Otherwise append within the innermost
			# level.
			for i, (level, node) in enumerate(state["stack"]):
				if psty == level:
					# pop to just above this level
					state["stack"] = state["stack"][:i]
					break
			
			level = make_node(state["stack"][-1][1], "level", None)
			make_node(level, "type", psty)
			if level_number: make_node(level, "num", level_number)
			if level_title: make_node(level, "heading", level_title)
			state["stack"].append( (psty, level) )

			if sec is not None: do_paragraph_indentation(sec)
			sec = None

	if sec is not None: do_paragraph_indentation(sec)

def do_paragraph_indentation(node):
	# The Lexis file does not encode paragraph indentation at all. We want to explicitly
	# represent the indentation levels of paragraphs by nesting <level> nodes. We must
	# infer the nesting from the numbering. For instance (1) followed by (2) are <level>s
	# with the same parent node, but (1) followed by (a) could represent either moving
	# in a level, or popping up to a higher level.

	# Get the numbering corresponding to each child node. For child nodes
	# that do not have numbering, return None.
	def get_num(n):
		n = n.xpath("string(num)")
		m = re.match("\((.*)\)$", n) # don't use re_match because it gets in the way of the calling function
		if m:
			return m.group(1)
		m = re.match("(.*)\.$", n)
		if m:
			return m.group(1)
		return None
	children = node.xpath("*")
	nums = [get_num(child) for child in children]

	# Create blocks of consecutive non-None values so that we leave the None blocks alone.
	list_of_nodes = [[]]
	list_of_nums = [[]]
	for child, num in zip(children, nums):
		if num is None:
			if len(list_of_nodes[-1]) != 0:
				list_of_nodes.append([])
				list_of_nums.append([])
		else:
			list_of_nodes[-1].append(child)
			list_of_nums[-1].append(num)
	if len(list_of_nodes[-1]) == 0:
		list_of_nodes.pop(-1)
		list_of_nums.pop(-1)

	from infer_list_indentation import infer_list_indentation
	for clist, nlist in zip(list_of_nodes, list_of_nums):
		# Infer child node indentation levels based on the paragraph numbering.
		# This is pretty slow becaues I wrote a kind of over-engineered linear
		# programming module for this task.
		try:
			result = infer_list_indentation(nlist)
		except ValueError as e:
			# Don't change anything in this block.
			print(e, file=sys.stderr)
			print(nlist, file=sys.stderr)
			print("", file=sys.stderr)
			continue

		def form_indent(nodes, symbols, parent_node):
			prev_node = None
			for s in symbols:
				if isinstance(s, list):
					form_indent(nodes, s, prev_node)
				else:
					prev_node = nodes.pop(0)
					if parent_node is not None:
						parent_node.append(prev_node)

		form_indent(clist, result, None)

def runs_to_node(node, runs):
	if len(runs) == 0: return
	runs[-1]["text"] = runs[-1]["text"].rstrip()

	# Appending text inside a mixed-content node is a bit complicated with lxml.
	for r in runs:
		# Remove default properties.
		if r["properties"].get("font") == "Times New Roman":
			del r["properties"]["font"]

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
			rn = make_node(node, "span", r["text"])
			sty = ""
			for k, v in r["properties"].items():
				if k == "b" and v:
					sty += "font-weight: bold; "
				elif k == "i" and v:
					sty += "font-style: italic; "
				elif k == "u" and v:
					sty += "text-decoration: underline; "
				elif k in ('b', 'i', 'u') and not v:
					pass
				elif k == "style" and v == "terminal":
					sty += "font-family: monospace; "
				else:
					raise ValueError(repr((k,v)))
			rn.set("style", sty)

def para_text_content(p):
	return "".join(r["text"] for r in p["runs"]).strip()
	
M = None
def re_match(pattern, string, dollar_sign=True, case_sensitive=False):
	# This is a helper utility that returns the match value
	# but also stores it in a global variable so we can still
	# get it.
	global M
	M = re.match(pattern + ("$" if dollar_sign else ""), string, re.I if not case_sensitive else 0)
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

main()

