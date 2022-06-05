# Docuemntation

We use [Sphinx](https://www.sphinx-doc.org/en/master/) to generate our documentation. It can be built in any form (text, HTML, or LaTeX) as an
advantage. To build it in HTML as exmaple, run the follwoing commands from this current directory. 

1. 
    ```bash
   sphinx-apidoc -o . ../src/
    ```

2. 
    ```bash
   make clean html
    ```