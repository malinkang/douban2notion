
---
2024.11.22
该项目暂停使用，目前项目中的热力图是通过将数据发送到原博主的服务器https://heatmap.malinkang.com/  进行渲染，目前不清楚数据泄露风险

---


# 将豆瓣电影和读书同步到Notion


本项目通过Github Action每天定时同步豆瓣电影和读书到Notion。

本项目原作者[malinkang](https://github.com/malinkang/)，感谢大佬的开源项目

在开始之前，你需要准备这些东西

1.一个豆瓣号，上面记录了图书，电影记录。

2.一个notion账号（需要梯子）



这个项目使用起来很简单，只需要4步。

1.Fork原作者的项目；

2.获取变量
共需要获取如下七个变量

DOUBAN_NAME（豆瓣id）

BOOK_NOTION_TOKEN

MOVIE_NOTION_TOKEN 	

NOTION_BOOK_URL	  

NOTION_MOVIE_URL

BOOK_NAME	         图书热力图上展示的标题

MOVIE_NAME	         电影热力图上展示的标题


其中豆瓣id，你自己去看就行，记下。图书/电影热力图的标题，你随便起。剩下的四个变量通过如下链接获取。

电影授权链接：[电影授权](https://api.notion.com/v1/oauth/authorize?client_id=268e6dd5-232d-4adb-829f-d7160d4b2dd7&response_type=code&owner=user&redirect_uri=https%3A%2F%2Fnotion-auth.malinkang.com%2Fdoubanmovie-oauth-callback)

图书授权链接：[图书授权](https://api.notion.com/v1/oauth/authorize?client_id=8104f931-8034-44a7-9f8d-80def25b9db6&response_type=code&owner=user&redirect_uri=https%3A%2F%2Fnotion-auth.malinkang.com%2Fdoubanbook-oauth-callback)


3.设置变量
在项目的  Settings->Secrets and variables->New repository secret  下，依次输入上述七个变量。

4.运行工作流
点击  Action->douban movie sync->Run workflow  启动电影同步
点击  Action->douban book sync->Run workflow   启动图书同步

一般来说，不会一切顺利。 

祝你好运。



