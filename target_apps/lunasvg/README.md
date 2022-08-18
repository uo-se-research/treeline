# [LunaSVG](https://github.com/sammycage/lunasvg)

We obtain the latest version at the time of our test (2.3.2).
The source file is provided here for reference under the [src](./src) directory.
However, if you wish to download the source file yourself, you can try the official release 
[download link](https://github.com/sammycage/lunasvg/archive/refs/tags/v2.3.2.tar.gz).

## Application Stats

```bash
cloc --not-match-f=test .
     134 text files.
     123 unique files.                                          
      41 files ignored.

github.com/AlDanial/cloc v 1.70  T=0.88 s (106.3 files/s, 24926.5 lines/s)
-------------------------------------------------------------------------------
Language                     files          blank        comment           code
-------------------------------------------------------------------------------
C++                             22           1068             54           5419
C                               10           1284            519           5387
C/C++ Header                    28            793           1329           2961
make                             6            577            354           1041
CMake                           24            112             70            721
Markdown                         1             25              0             64
YAML                             2              4              1             30
-------------------------------------------------------------------------------
SUM:                            93           3863           2327          15623
-------------------------------------------------------------------------------
```

We only count code of C, C++, and C/C++ Headers (given *test* files are excluded).
Thus, 5,419 + 5,387 + 2,961 = 13,767 SLoC.

## Run With AFL

To manually run the AFL listener on the target application you use a command similar to the one below.

```bash
afl-treeline -i /home/treeline/target_apps/lunasvg/inputs -o /home/results/lunasvg-001 -p -N 60 -d svg2png @@
```
