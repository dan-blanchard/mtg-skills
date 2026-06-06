"""Tests for Scryfall image-URL extraction (deck-forge)."""

from mtg_utils._deck_forge.images import image_urls


def test_normal_card_returns_small_normal_art_crop():
    card = {
        "name": "Llanowar Elves",
        "image_uris": {
            "small": "https://img/small.jpg",
            "normal": "https://img/normal.jpg",
            "large": "https://img/large.jpg",
            "png": "https://img/card.png",
            "art_crop": "https://img/art.jpg",
            "border_crop": "https://img/border.jpg",
        },
    }
    assert image_urls(card) == {
        "small": "https://img/small.jpg",
        "normal": "https://img/normal.jpg",
        "art_crop": "https://img/art.jpg",
    }


def test_dfc_without_top_level_images_uses_front_face():
    card = {
        "name": "Hengegate Pathway // Mistgate Pathway",
        "card_faces": [
            {
                "name": "Hengegate Pathway",
                "image_uris": {
                    "small": "https://img/front-small.jpg",
                    "normal": "https://img/front-normal.jpg",
                    "art_crop": "https://img/front-art.jpg",
                },
            },
            {
                "name": "Mistgate Pathway",
                "image_uris": {
                    "small": "https://img/back-small.jpg",
                    "normal": "https://img/back-normal.jpg",
                    "art_crop": "https://img/back-art.jpg",
                },
            },
        ],
    }
    result = image_urls(card)
    # Front-face sizes power thumbnails/banner …
    assert result["small"] == "https://img/front-small.jpg"
    assert result["normal"] == "https://img/front-normal.jpg"
    assert result["art_crop"] == "https://img/front-art.jpg"
    # … plus BOTH faces' normal images so the preview can show both sides.
    assert result["faces"] == [
        {"name": "Hengegate Pathway", "normal": "https://img/front-normal.jpg"},
        {"name": "Mistgate Pathway", "normal": "https://img/back-normal.jpg"},
    ]


def test_single_face_card_has_no_faces_key():
    card = {"name": "Llanowar Elves", "image_uris": {"normal": "https://img/n.jpg"}}
    assert "faces" not in image_urls(card)


def test_missing_images_returns_none():
    assert image_urls({"name": "No Art Card"}) is None


def test_partial_image_uris_only_returns_present_keys():
    card = {"name": "Partial", "image_uris": {"normal": "https://img/normal.jpg"}}
    assert image_urls(card) == {"normal": "https://img/normal.jpg"}
