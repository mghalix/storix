import storix as sx


fs = sx.LocalFilesystem()
fs.mkdir('test-dir')
fs.touch('test-dir/hello.txt', 'Hello World!')
fs.rmdir('test-dir', recursive=True)
