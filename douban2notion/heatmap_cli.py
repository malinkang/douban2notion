import pendulum


def count_tracks(loader):
    """Count one activity for each dated Notion page."""
    results = loader.get_api_data()
    for result in results:
        date = (result.get("properties") or {}).get(loader.date_prop_name, {}).get(
            "date"
        )
        if not date or not date.get("start"):
            continue
        date_key = pendulum.parse(date["start"]).to_date_string()
        loader.number_by_date_dict[date_key] = (
            loader.number_by_date_dict.get(date_key, 0) + 1
        )
    loader.number_list.extend(loader.number_by_date_dict.values())


def _count_track_dict(self):
    count_tracks(self)


def main():
    # The upstream GitHub Heatmap Notion loader assumes a numeric value column
    # such as "看过" or "读过". Legacy Douban templates often only contain the
    # title and date columns, so count dated pages instead.
    from github_heatmap.loader.notion_loader import NotionLoader

    NotionLoader.make_track_dict = _count_track_dict
    from github_heatmap.cli import run

    run()


if __name__ == "__main__":
    main()
