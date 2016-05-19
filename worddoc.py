# This module contains a function called open_docx(filename) which opens
# a .docx file and returns a simplified data structure for document content,
# with error checking for nodes that it does not recognize.
#
# The format is:
#
# document = {
#    "header": [list of sections, similer to the body sections below],
#    "sections": [
#       { # a section
#           "properties": {
#                "type": "nextPage" | "continuous" # the break type at the end of this section
#           }
#           "paragraphs": [
#                { # a paragraph
#                    "properties": {
#                         "align": "center" | "both" (jusified) | "distribute" | "end" | "numTab" | "start"
#                         "style": "name of style",
#                         "frame": { frame properties if a frame },
#                         "indentation": 0,
#                         "following_line_indentation": 0, # after the first line (total indentation), the opposite of how first-line hanging indents are specified by the user
#                         "tabs": [ 100, 200, 300 ], # custom tab stops
#                     },
#                    "runs": [ # individual runs of text within the paragraph
#                         { # a text run
#                             "properties": {
#                                  "b": True, # bold
#                                  "i": True, # italic
#                                  "u": True, # underline
#                                  "smallCaps": True, # small caps
#                             },
#                             "text": "the text" # contains \n's and \t's.
#                         }
#                     ],
#                }
#           ]
#       }
#    ]
# }

import zipfile, lxml.etree, re
from math import floor
from copy import deepcopy
import sys

wpns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
	
def open_docx(fn, **handlers):
	with zipfile.ZipFile(fn) as z:
		# Load the document body.
		document = lxml.etree.parse(z.open("word/document.xml")).getroot()
	
		# Load any first header, if one exists.
		try:
			header = lxml.etree.parse(z.open("word/header1.xml")).getroot()
		except KeyError:
			header = None

	return {
		"header": process_paragraphs(header, handlers) if header is not None else None,
		"sections": process_document_body(document, handlers),
	}

def process_document_body(document, handlers):
	if document.tag != wpns + "document": raise ValueError("Invalid document type: {}; expected: {}.".format(document.tag, wpns + "document"))
	for node in document:
		if node.tag != wpns + "body": raise ValueError("Unexpected element.")
		return process_paragraphs(node, handlers)
	raise ValueError("Did not encounter body node.")
		
def process_paragraphs(node, handlers):
	sections = [ ]
	
	def add_sec():
		sections.append({ "properties": None, "paragraphs": [] })
	add_sec()
	
	for pnode in node:
		if pnode.tag == wpns + "p":
			p = process_paragraph(pnode, handlers)
			
			# Treat <br>'s followed by tabs in runs as paragraph separators.
			# I did this originally for DC Statutes. Not sure if it's useful
			# for the DC Code.
			er = explode_runs(p["runs"])
			for i, run_group in enumerate(er):
				# Clone the original paragraph to preserve attributes besides the runs themselves,
				# and then replace the runs with just this set of runs from the original.
				p1 = deepcopy(p)
				p1["runs"] = run_group
				del p1["section_properties"]
				
				# Handle hanging indents by overriding the indentation on this paragraph.
				if i > 0: p1["indentation"] = p.get("following_line_indentation", p.get("indentation", 0))
				convert_tabs_to_indentation(p1)
				
				# Append to the current section.
				sections[-1]["paragraphs"].append(p1)
				
			if p["section_properties"] is not None:
				# This paragraph ends a section. Set the section properties
				# and start a new section.
				sections[-1]["properties"] = p["section_properties"]
				add_sec()
			del p["section_properties"]
					
		elif pnode.tag == wpns + "sectPr":
			# Section properties for the final section in the document.
			sections[-1]["properties"] = process_section_properties(pnode)
		
		elif pnode.tag == wpns + "tbl":
			if not pnode.xpath("//w:t", namespaces={"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}):
				# This table has no text content so it is safe to skip.
				# I hope!
				continue
			sections[-1]['paragraphs'].append({
				"properties": {},
				"runs": [{"properties": {}, "text": "@@TABLE@@"}]
			})
			print("Tables are not implemented.", file=sys.stderr)
			# dump(pnode)

		else:
			print("Unhandled body node.", file=sys.stderr)
			dump(pnode)
			
	return sections

def process_paragraph(para_node, handlers):
	runs = []
	properties = { }
	default_run_properties = { }
	field_state = None
	section_properties = None
	
	for node in para_node:
		tag = re.sub("^\{http://schemas.openxmlformats.org/wordprocessingml/2006/main\}", "w:", node.tag)
		if tag == "w:pPr":
			for prnode in node:
				prtag = re.sub("^\{http://schemas.openxmlformats.org/wordprocessingml/2006/main\}", "w:", prnode.tag)
				if prtag == "w:rPr":
					default_run_properties.update(process_run_properties(prnode))
				elif prtag in ("w:adjustRightInd", "w:widowControl", "w:autoSpaceDE", "w:autoSpaceDN", "w:spacing", "w:contextualSpacing", "w:shd"):
					# Properties we really don't care about.
					pass
				elif prtag == "w:sectPr":
					# Properties of the section that ends here.
					section_properties = process_section_properties(prnode)
				elif prtag == "w:jc":
					# text alignment, but treat "left" as the default by not including it in output
					if prnode.get(wpns + "val") != "left":
						properties['align'] = prnode.get(wpns + "val")
				elif prtag == "w:textAlignment": # and prnode.get(wpns + "val") == "auto":
					# this is vertical alignment; don't care
					pass
				elif prtag == "w:keepLines" or prtag == "w:keepNext":
					# this is when to force content to new pages
					pass
				elif prtag == "w:suppressAutoHyphens":
					# this is when suppressing hyphenation; don't care
					pass
				elif prtag == "w:kinsoku":
					# don't care about left/right language
					pass
				elif prtag == "w:overflowPunct":
					# don't care if we allow punctuation to go outside margin
					pass
				elif prtag == "w:pBdr":
					# don't care about borders
					pass
				elif prtag == "w:outlineLvl":
					properties['outlineLvl'] = prnode.get(wpns + "val") # outline level
				elif prtag == "w:numPr":
					properties["num"] = {
						"ilvl": prnode.getchildren()[0].get(wpns + 'val'),
						"numId": prnode.getchildren()[1].get(wpns + 'val'),
					}
				elif prtag == "w:pStyle":
					properties['style'] = prnode.get(wpns + "val")
				elif prtag == "w:framePr":
					properties['frame'] = { re.sub("^\{http://schemas.openxmlformats.org/wordprocessingml/2006/main\}", "", k): v for (k,v) in prnode.attrib.items() }
				elif prtag == "w:ind":
					# Indentation, which we might want to use in an advisory way to determine list levels.
					i1 = int(prnode.get(wpns + "left", "0")) + int(prnode.get(wpns + "firstLine", "0"))
					i2 = int(prnode.get(wpns + "left", "0"))
					if i1 != 0: properties["indentation"] = i1
					if i2 != 0 and i2 != i1: properties["following_line_indentation"] = i2
				elif prtag == "w:tabs":
					# Custom tab stops, which we might want to use in an advisory way to determine list levels.
					properties["tabs"] = []
					for ts in prnode:
						if ts.tag == wpns + "tab":
							properties["tabs"].append(int(ts.get(wpns + "pos", "0")))
				else:
					print("Unhandled paragraph properties node.", file=sys.stderr)
					dump(prnode)
		elif tag in ("w:bookmarkStart", "w:bookmarkEnd", "w:proofErr"):
			# Nothing interesting.
			pass
		elif tag == "w:r":
			run = process_run(node, default_run_properties, handlers)
			
			# update the current field state, and skip instruction text when we're in the begin state
			field_state = run["properties"].get("field_state", field_state)
			if field_state == "begin": continue # skip all runs while in the "begin" state
			if "field_state" in run["properties"]: continue # skip runs that just have a field state change
			
			# Combine the run with the previous run if it has the same properties
			# to make pattern matching easier. Various markup things can break a
			# logical run into smaller pieces in ways we don't care about. Also
			# combine if the run or previous run only contains whitespace, for
			# convenience, since formatting changes may be spurrious here.
			if len(runs) > 0 and (runs[-1]["properties"] == run["properties"] or run["text"].strip() == "" or runs[-1]["text"].strip() == ""):
				runs[-1]["text"] += run["text"]
			else:
				runs.append(run)
		elif tag == "w:hyperlink":
			for hypernode in node:
				hypertag = re.sub("^\{http://schemas.openxmlformats.org/wordprocessingml/2006/main\}", "w:", hypernode.tag)
				if hypertag == "w:r":
					run = process_run(hypernode, default_run_properties, handlers)
					# update the current field state, and skip instruction text when we're in the begin state
					field_state = run["properties"].get("field_state", field_state)
					if field_state == "begin": continue # skip all runs while in the "begin" state
					if "field_state" in run["properties"]: continue # skip runs that just have a field state change
					
					# Combine the run with the previous run if it has the same properties
					# to make pattern matching easier. Various markup things can break a
					# logical run into smaller pieces in ways we don't care about. Also
					# combine if the run or previous run only contains whitespace, for
					# convenience, since formatting changes may be spurrious here.
					if len(runs) > 0 and (runs[-1]["properties"] == run["properties"] or run["text"].strip() == "" or runs[-1]["text"].strip() == ""):
						runs[-1]["text"] += run["text"]
					else:
						runs.append(run)
				else:
					print("Unhandled hypertext node:", hypertag, file=sys.stderr)
					dump(node)					
		else:
			print("Unhandled paragraph content node:", tag, file=sys.stderr)
			dump(node)

	return {
			"properties": properties,
			"runs": runs,
			"section_properties": section_properties,
			}
			
def explode_runs(runs):
	# Treat <br>'s followed by tabs in runs as paragraph separators.
	paragraphs = [[]]
	for run in runs:
		for i, run_part in enumerate(run["text"].split("\n\t")):
			if i > 0 and len(paragraphs[-1]) > 0:
				paragraphs.append([]) # start a new paragraph
			paragraphs[-1].append({
				"text": ("\t" if i > 0 else "") + run_part, # put the tab back
				"properties": run["properties"],
			})
	return paragraphs
			
def convert_tabs_to_indentation(p):
	# Convert leading tab characters in the first run of the paragraph into indentation.
	if len(p['runs']) == 0: return
	first_run = p['runs'][0]
	properties = p['properties']
	while first_run["text"].startswith("\t"):
		# Get the next tab stop. It's the next custom tab stop greater than
		# the current indentation amount, or if there is no such tab stop
		# then the next default tab stop at 0.5" (720 point) intervals.
		cur_indent = properties.get("indentation", 0)
		for tab_stop in properties.get("tabs", []):
			if tab_stop > cur_indent:
				next_indent = tab_stop
				break
		else:
			# No custom tab stop, so use a default tab stop.
			next_indent = (floor(cur_indent/720)+1) * 720
		properties["indentation"] = next_indent
		first_run["text"] = first_run["text"][1:] # chop off the initial tab
	
	
def process_run(run_node, default_run_properties, handlers):
	text = ""
	
	properties = { }
	properties.update(default_run_properties)
	
	for node in run_node:
		tag = re.sub("^\{http://schemas.openxmlformats.org/wordprocessingml/2006/main\}", "w:", node.tag)
		if tag == "w:t":
			text += node.text
		elif tag == "w:br":
			text += "\n" # we'll turn this back into line breaks at the end
		elif tag == "w:tab":
			text += "\t" # we'll turn this back into something else at the end
		elif tag == "w:rPr":
			properties.update(process_run_properties(node))
		elif tag == "w:lastRenderedPageBreak":
			# advisory only
			pass
		elif tag == "w:fldChar":
			# This run content node indicates the start or end of a complex field value,
			# like a page number. When @fldCharType is begin, subsequent runs give
			# the field instructions until another w:fldChar node with @fldCharType
			# set to "separate", after which the subsequent runs give the most current
			# field value, or a w:fldChar node with @fldCharType set to "end" which ends
			# the field instruction or current value. We'll process this during paragraph
			# processing.
			properties["field_state"] = node.get(wpns + "fldCharType")
		elif tag == "w:instrText":
			# we'll cut this out at a higher level, but for debugging include the field
			# instruction in the run text as raw XML
			text += lxml.etree.tostring(node, pretty_print=True, encoding=str)
		elif tag == "w:drawing" and "drawing" in handlers:
			text += handlers["drawing"](node)
		elif tag == "w:pict" and "pict" in handlers:
			text += handlers["pict"](node)
		elif tag == "w:pgNum":
			text += "??PAGENUM??"
		elif tag == "w:noBreakHyphen":
			text += "-"
		elif tag == "w:cr":
			text += "\n"
		else:
			print("Unhandled run content node.", file=sys.stderr)
			dump(node)
	return { "text": text, "properties": properties }
	
def process_run_properties(node):
	properties = { }
	for pr in node:
		tag = re.sub("^\{http://schemas.openxmlformats.org/wordprocessingml/2006/main\}", "", pr.tag)
		if tag in ("b", "i", "u", "smallCaps", "caps", "strike"):
			# TODO: Are these toggle properties and what does that mean?
			properties[tag] = (pr.get(wpns + "val", "true") == "true")
			
		elif tag == "rFonts":
			properties["font"] = pr.get(wpns + "ascii") # there are several font possibilities depending on the character type, it seems

		elif tag == "rStyle":
			properties["style"] = pr.get(wpns + "val") # style name

		elif tag in ("sz", "szCs", "color", "vertAlign", "bCs", "noProof", "highlight", "iCs", "vanish"):
			# I don't think we care. Highlight seems like maybe we should print a warning.
			pass
		
		elif tag == "lang": # and pr.get(wpns + "val") == "en-US":
			# don't care if we're setting language to English
			pass
		elif tag == "webHidden":
			# don't care whether this should be shown on the web
			pass
		elif tag == "w":
			# don't care about window width
			pass
		elif tag == "bdr":
			# don't care about borders
			pass
		elif tag == "spacing":
			properties["spacing"] = pr.get(wpns + "val")
		elif tag == "shd":
			properties["shading"] = {k.split('}')[1]: v for k, v in pr.attrib.items()}
		else:
			print("Unhandled run properties node.", file=sys.stderr)
			dump(pr)
	return properties
	
def process_section_properties(node):
	properties = { }
	for pr in node:
		tag = re.sub("^\{http://schemas.openxmlformats.org/wordprocessingml/2006/main\}", "", pr.tag)
		
		if tag in ("headerReference", "footerReference", "pgSz", "pgMar", "formProt", "textDirection", "docGrid", "cols", "noEndnote"):
			# don't care
			pass

		elif tag in ("pgNumType",):
			# probably don't care
			pass
		
		elif tag == "type" and pr.get(wpns + "val") in ("continuous", "nextPage"):
			properties["type"] = pr.get(wpns + "val")
			
		elif tag == "type" and pr.get(wpns + "val") == "nextPage":
			# This is the typical section break type.
			pass
		elif tag == "lnNumType":
			properties["linenumbertype"] = {k.split('}')[1]: v for k, v in pr.attrib.items()}
		else:
			print("Unhandled section properties node.", file=sys.stderr)
			dump(pr)
	return properties
	
def dump(node):
	# clone the node to get rid of extraneous namespaces
	elem = lxml.etree.Element(node.tag, node.attrib)
	elem.text = node.text
	elem.tail = node.tail
	elem[:] = node
	node = elem
	
	print(lxml.etree.tostring(node, pretty_print=True, encoding=str), file=sys.stderr)
