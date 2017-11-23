# shfrp
Reactive (non-functional) programming for the command line. A spreadsheet without the sheet that interacts with bash.

# Usage
```
# Print name whenever it changes
shfrp run 'echo {name}'

# Update the parameter name to "Jim"
shfrp set name Jim
```
# Caveats

This tool is currently made of chewing gum, glue and bits of paper. This is likely non suitable for high performance data processing.

The concept of "saving your spreadsheet" becomes quite nebulous. When bits of it are on the command line.


# Motivation

The shell is a wonderful tool for prototyping. [Small tools](http://wiki.c2.com/?UnixDesignPhilosophy) can be quickly [chained together](https://www.gnu.org/software/bash/manual/html_node/Pipelines.html) to solve specific problems.

This tool extends what can be done with [bash one-liners](http://www.bashoneliners.com/) by allowing one to recalculate and redisplay bash one-liners in response to changes in data and user-specified parameters. This is analogous to [what if calculations in spreadsheets](https://support.office.com/en-us/article/Introduction-to-What-If-Analysis-22bffa5f-e891-4acc-bf7a-e4645c446fb4), where, for example, a single cell can be changed and the results immediately displayed.

Given that shell is a designed (and regularly used) as a glue language, one can use it for very general purpose display functionality. For example, one might [render and display networks](http://graphviz.org/) in response to new data. As such, this tool might be considered an analogue of tools like [Angular](https://angularjs.org/) or [React](https://reactjs.org/) but in the space of command-line tools rather than that of *Javascript*, though *shfrp* does not really deal with "partial update of data displays."

Command-line tools that address similar problems include [watch](https://linux.die.net/man/1/watch), [tmuxinator](https://github.com/tmuxinator/tmuxinator), [conky](https://github.com/brndnmtthws/conky).


The space of [functional (and non-functional) reactive programming](https://en.wikipedia.org/wiki/Functional_reactive_programming) is fairly crowded. This tool isn't really a natural bed-fellow of these tools. Tools like (Analytica)[http://www.lumina.com/] liberate the functional reactive programming of spreadsheets and place it instead in the language of "influence diagrams" (a business / modelling term for directed acyclic graphs). [Make](https://www.gnu.org/software/make/) deals with partial recalculation of dependency graphs using bash scripts, though is couched in terms of changes to files and manual recalculation.


# Alternatives and prior work

* Spreadsheets (like excel) are the quintessential example of functional reactive programming.
* The commercial tool Analytica extends the idea of a spreadsheet to an "influence digram" (basically a dependency graph).
