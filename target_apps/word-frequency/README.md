# Word Frequency (Fedora 27 RPM repository)

Similar to PerfFuzz we use version wf-0.41. Word Frequency is a simple word counter found in
[Fedora 27 RPM repository](https://pkgs.org/). The package with the version specified is available here. However,
if you would like to download it from the source, you may try 
[this link](http://ftp.altlinux.org/pub/distributions/ALTLinux/Sisyphus/x86_64/SRPMS.classic/wf-0.41-alt2.src.rpm).

## Application Stats
```commandline
$ cloc --not-match-f=test .
      32 text files.
      25 unique files.                              
      16 files ignored.

github.com/AlDanial/cloc v 1.70  T=0.16 s (98.6 files/s, 59516.1 lines/s)
--------------------------------------------------------------------------------
Language                      files          blank        comment           code
--------------------------------------------------------------------------------
Bourne Shell                      5            666            754           4709
make                              4            110             41            916
Bourne Again Shell                2             91            111            843
m4                                1             92             14            768
C                                 2             66             49            279
C/C++ Header                      2             19             13            115
--------------------------------------------------------------------------------
SUM:                             16           1044            982           7630
--------------------------------------------------------------------------------
```
We only count code of C and C/C++ Headers (given *test* files are excluded). Thus, 279 + 115 = 394. 

## Build

First uncompressing the file following these commands
```commandline
rpm2cpio wf-0.41-alt1.qa1.src.rpm | cpio -idmv
tar -xvf wf-0.41.tar
```
From withing the new source directory `wf-0.41`, US AFL's compiler to 
generate the appropriate Makefile.

```commandline
CC=/home/git/perffuzz/afl-clang-fast ./configure
```

Then run `make` to build the application with the appropriate instrumentation.

If things compiled successfully, you should find a file named `wf` under `target_apps/word-frequency/src/wf-0.41/src`.

## Sample run with no fuzzing

To test the that the installation was successfully completed. You can run `wf` based on 
[seed.txt](inputs/seed.txt) (shown below) by simply passing the file to wf `./src/wf-0.41/src/wf inputs/seed.txt`. A correct
run should result on a report of how many times a word was repeated (ones in this case). 

```text
dummy seed input for perffuzz
```

## Run with AFL

To run the AFL listener on the target application you use a command similar to the one below.

```commandline
afl-fuzz -i /home/treeline/target_apps/word-frequency/inputs/ -o /home/results/wf-001 -p -N 60 -d /home/treeline/target_apps/word-frequency/src/wf-0.41/src/wf
```
