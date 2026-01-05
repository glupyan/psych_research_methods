# Grad Research Methods — Module-free Hugo/blogdown Site

## Build locally (R)

### R Package install
```
install.packages("blogdown")
blogdown::install_hugo(version = "0.125.7", extended = TRUE)
blogdown::build_site()
blogdown::serve_site()
```

### (Re)build the site
Change the paths in Makefile to point to the appropriate .bib and .md files
```make build```

This will rebuild the schedule using the bibtex codes in schedule.md and then rebuild the rest of the site.


## Deploy on Netlify
`netlify.toml` sets the Hugo version and build command.

