import argparse
import glob
import os
import shutil
import time
from douban2notion.notion_helper import NotionHelper

def move_and_rename_file(type):

    # 确保目标目录存在
    source_path = os.path.join("./OUT_FOLDER", 'notion.svg')
    target_dir = os.path.join("./OUT_FOLDER", type)
    os.makedirs(target_dir, exist_ok=True)

    # 生成时间戳命名的文件名
    timestamp = int(time.time())
    new_filename = f"{timestamp}.svg"
    target_path = os.path.join(target_dir, new_filename)

    # 移动并重命名文件
    shutil.move(source_path, target_path)
    # 返回移动后的文件路径
    return target_path
    
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("type")
    options = parser.parse_args()
    type = options.type
    notion_helper = NotionHelper(type)
    image_file = move_and_rename_file(type)
    if image_file:
        image_url = f"https://raw.githubusercontent.com/{os.getenv('REPOSITORY')}/{os.getenv('REF').split('/')[-1]}/{image_file[2:]}"
        heatmap_url = f"https://heatmap.malinkang.com/?image={image_url}"
        if notion_helper.heatmap_block_id:
            response = notion_helper.update_heatmap(
                block_id=notion_helper.heatmap_block_id, url=heatmap_url
            )
if __name__ == "__main__":
    main()