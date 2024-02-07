import argparse
import os
from utils import upload_image
from notion_helper import NotionHelper
def get_file():
    # 设置文件夹路径
    folder_path = './OUT_FOLDER'

    # 检查文件夹是否存在
    if os.path.exists(folder_path) and os.path.isdir(folder_path):
        entries = os.listdir(folder_path)
        
        file_name = entries[0] if entries else None
        return file_name
    else:
        print("OUT_FOLDER does not exist.")
        return None
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("type")
    options = parser.parse_args()
    type = options.type
    is_movie = True if type=="movie" else False
    notion_url = os.getenv("NOTION_MOVIE_URL") if is_movie else os.getenv("NOTION_BOOK_URL")
    notion_helper = NotionHelper(notion_url)
    image_file = get_file()
    if image_file:
        image_url = upload_image(f"heatmap/{os.getenv('REPOSITORY').split('/')[0]}",image_file,f"./OUT_FOLDER/{image_file}")
        block_id = notion_helper.image_dict.get("id")
        if(image_url and block_id):
            notion_helper.update_image_block_link(block_id,image_url)