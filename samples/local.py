from storix import LocalFilesystem


fs = LocalFilesystem('.', sandboxed=True)
fs.cd('sample-files')

content_data: bytes
content: str

content_data = fs.cat('foo.txt')
content = content_data.decode()
print(content)
