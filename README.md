# shfrp

Reactive (non-functional) programming for the command line.

# Usage

```
# Repeatedly print name whenever it changes
shfrp run 'echo {name}'

# Update the value of jim
shfrp set name Jim
```

# Caveats

This tool is currently made of chewing gum, glue and bits of paper. This is likely non suitable for high performance data munging.

The concept of "saving your spreadsheet" becomes quite nebulous. When bits of it are on the command line.

# Alternatives and prior work

* Spreadsheets (like excel) are the quintessential example of functional reactive programming.
* The commercial tool Analytica extends the idea of a spreadsheet to an "influence digram" (basically a dependency graph).
