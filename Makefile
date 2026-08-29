BIB=content/bib/grad_methods.bib
SCHED_IN=content/schedule_bib.md
SCHED_OUT=content/schedule.md

expand:
	-Rscript -e "rmarkdown::render('../markdown_syllabus_grad_methods/grad_methods_syllabus.Rmd', output_format = 'pdf_document')"
	-cp ../markdown_syllabus_grad_methods/grad_methods_syllabus.pdf static/	
	-python export_syllabus_from_markdown.py ../markdown_syllabus_grad_methods/grad_methods_syllabus.Rmd > content/schedule_bib.md
	-cp ../markdown_syllabus_grad_methods/grad_methods.bib content/bib
	python build_schedule.py --in $(SCHED_IN) --out $(SCHED_OUT) --bib $(BIB) --start 2026-01-21


build: expand
	Rscript -e "blogdown::build_site()"
