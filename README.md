# 将豆瓣电影和读书同步到Notion


本项目通过Github Action每天定时同步豆瓣电影和读书到Notion。

本项目原作者[malinkang](https://github.com/malinkang/)，感谢大佬的开源项目

电影授权链接：[电影授权](https://api.notion.com/v1/oauth/authorize?client_id=268e6dd5-232d-4adb-829f-d7160d4b2dd7&response_type=code&owner=user&redirect_uri=https%3A%2F%2Fnotion-auth.malinkang.com%2Fdoubanmovie-oauth-callback)
图书授权链接：[图书授权](https://api.notion.com/v1/oauth/authorize?client_id=8104f931-8034-44a7-9f8d-80def25b9db6&response_type=code&owner=user&redirect_uri=https%3A%2F%2Fnotion-auth.malinkang.com%2Fdoubanbook-oauth-callback)