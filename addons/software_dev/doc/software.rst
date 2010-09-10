=== Software development ===


The structure of the software development schema is divided into 
logical groups of operations:
    - Packages: the pieces that make a software project up
    - Code: the repositories, series, branches and commits of the code
    - Buildbot: the machines that can test the software, and their state
    - Tests: the results of software building and testing.


Package
---------

A software package is a product that we want to build. It is comprised
of components.


=========
The code of this module can also take care of a local mirror of code,
which will proxy the public (and slow) repositories. The builds will fetch
code from the local mirror instead of the public repositories, to
minimize downloads from the Internet.

