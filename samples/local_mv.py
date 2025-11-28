from storix import LocalFilesystem


fs = LocalFilesystem()

fs.touch('hello.txt', 'Hello world!')
fs.mkdir('test-dir')
fs.mv('hello.txt', 'test-dir')
