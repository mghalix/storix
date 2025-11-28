from storix import LocalFilesystem

fs = LocalFilesystem()

fs.touch("hello.txt", "Hello world!")
fs.mkdir("test-dir")
fs.cp("hello.txt", "test-dir")
