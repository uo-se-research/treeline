# [JerryScript](https://jerryscript.net/)

We obtain version 2.4.0 to test it 
[download link](https://github.com/jerryscript-project/jerryscript/archive/refs/tags/v2.4.0.tar.gz). However, we apply a minor fix (see *Modification Details* below ) to build it with afl-clang-fast. Therefore, we recommend using the [modified version](./src) found here to replicate the test results. 

## Application Stats
```bash
$ cloc --not-match-f=test .
    1503 text files.
    1495 unique files.                                          
     183 files ignored.

github.com/AlDanial/cloc v 1.70  T=6.96 s (189.7 files/s, 37205.1 lines/s)
---------------------------------------------------------------------------------------
Language                             files          blank        comment           code
---------------------------------------------------------------------------------------
C                                      266          19737          24640          91369
JavaScript                             621           7589          10125          33559
C/C++ Header                           238           3924           9951          17434
Markdown                                35           5369              0          13317
make                                    12           2282           1062           4520
Python                                  19            991            691           3015
CMake                                   45            357            536           2316
JSON                                     3              0              0           1099
Tcl/Tk                                  17            103            230            875
C++                                     13            320            555            823
Bourne Shell                            17            113            268            551
INI                                      1              3              0            399
DOS Batch                               27              0              0            242
YAML                                     2             24              2            223
Assembly                                 2              7             66             69
Windows Module Definition                2              6              0             66
---------------------------------------------------------------------------------------
SUM:                                  1320          40825          48126         169877
---------------------------------------------------------------------------------------
```

We only count code of C, C++, and C/C++ Headers (given *test* files are excluded). Thus, 91,369 + 17,434 + 823 = 109,626.

## Manually Build the Source Code

After decompressing the file `tar -xvf jerryscript-2.4.0-modified.tar.gz`, and within the new directory,
use AFL's compiler to build the project.

```bash
CC=/home/git/perffuzz/afl-clang-fast python tools/build.py --clean --jerry-cmdline=on --lto=off
```
The options `--lto=off` disables link-time optimizations and `--jerry-cmdline=on` builds jerry command line tool.

## Sample Run Without Fuzzing

To test the that the installation was successfully completed. You can run `jerry` based on 
the [sample input](inputs/hello.js) (shown below) by simply passing the file to jerry `./src/jerryscript-2.4.0/build/bin/jerry inputs/hello.js`.

###### hello.js
```javascript
print ("Hello JerryScript!");
```

## Modification Details:
Changed the initialization of `ecma_typedarray_info_t info` found in `jerry-core/ecma/builtin-objects/typedarray/ecma-builtin-typedarray-prototype.c` from `{ 0 }` to an explicit zeroing `{ 0,0,0,0,0,0,0 }`! Otherwise, clang 3.8 will not build the application. See [issue #5020](https://github.com/jerryscript-project/jerryscript/issues/5020) for details of similar fix. 

## PerfFuzz Seeds:

We obtained PerfFuzz seeds from the tool repository itself. We looped over all the available .js files, removed all comments, and copied all the files of size < 61 bytes.

## Run with AFL

To run the AFL listener on the target application you use a command similar to the one below.

```bash
afl-treeline -i /home/treeline/target_apps/jerryscript/inputs -o /home/results/jerryscript-001 -p -t 10000 -N 60 -d /home/treeline/target_apps/jerryscript/src/jerryscript-2.4.0/build/bin/jerry @@
```