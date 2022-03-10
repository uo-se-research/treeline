# [libxml2](http://www.xmlsoft.org/)

## Download Instructions

Similar to PerfFuzz we use version libxml2-2.9.7. To download the source file you can use this 
[link](http://xmlsoft.org/sources/libxml2-2.9.7-rc1.tar.gz) or you can search for the same version in libxml2's 
[sources archive](http://xmlsoft.org/sources/).  

## Application Stats

```commandline
$ cloc --not-match-f=test .
    3748 text files.
    3135 unique files.                                          
    2861 files ignored.

github.com/AlDanial/cloc v 1.70  T=13.32 s (105.1 files/s, 39006.8 lines/s)
-------------------------------------------------------------------------------
Language                     files          blank        comment           code
-------------------------------------------------------------------------------
C                               89          19324          49549         162183
XML                            679           2721           1899          73165
HTML                           248           1319            225          64563
C/C++ Header                    73           3239           4796          29188
Bourne Shell                    16           4527           4832          26974
Python                          59           3460           7448          18663
m4                               9           1158            265          11111
XHTML                            3            583             22           5430
XSD                            155            532            324           5132
DTD                             30           1260           2770           4187
XSLT                            16            192            155           4067
make                            11            220             67           2003
JavaScript                       1             25             48            635
PHP                              4             14              1            512
DOS Batch                        2             49              0            209
Clean                            1             11              0            168
Perl                             2             16              0             69
CSS                              1              0              0             66
-------------------------------------------------------------------------------
SUM:                          1399          38650          72401         408325
-------------------------------------------------------------------------------
```

We only count code of C and C/C++ Headers (given *test* files are excluded). Thus, 162183 + 29188 = 191,371.

## Build

After uncompressing the file `tar -xvf libxml2-2.9.7.tar.gz`, and withing the new directory, US AFL's compiler to 
generate the appropriate Makefile.

```commandline
CC=/home/git/perffuzz/afl-clang-fast ./configure --disable-shared
```
We use the flag `--disable-shared` to complie in a static library mode.

Then run 
```commandline
make
```

If things compiled successfully, then you should find a file call `xmllint` which is the source file we use to run
tests.

## Sample run with no fuzzing

To test the that the installation was successfully completed. You can run `xmllint` based on 
[seed1.xml](inputs/seed1.xml) (shown below) by simply passing the file to libxml2 `./xmllint sample.dot`. A correct
run should result on the same xml file being printed. The file [seed1.xml](inputs/seed1.xml) is based on the example
given in [libxml2 documentation](http://www.xmlsoft.org/tutorial/apb.html). 

```xml
<?xml version="1.0"?>
<story>
  <storyinfo>
    <author>John Fleck</author>
    <datewritten>June 2, 2002</datewritten>
    <keyword>example keyword</keyword>
  </storyinfo>
  <body>
    <headline>This is the headline</headline>
    <para>This is the body text.</para>
  </body>
</story>
```

## Run with AFL

To run the AFL listener on the target application you use a command similar to the one below.

```commandline
afl-fuzz -i /home/treeline/target_apps/libxml2/inputs/ -o /home/results/libxml2-001 -p -N 500 -d /home/treeline/target_apps/libxml2/src/libxml2-2.9.7/xmllint @@
```
