from backend.parse import bbox_top_left


def test_bottom_left_converted():
    # A4 page (842 pt high); box 100 pt from the top, 20 pt tall, in bottom-left coords: t=742, b=722
    bb = bbox_top_left(50, 742, 200, 722, page_height=842, bottom_left=True)
    assert (bb.x0, bb.y0, bb.x1, bb.y1) == (50, 100, 200, 120)


def test_top_left_unchanged():
    bb = bbox_top_left(50, 100, 200, 120, page_height=842, bottom_left=False)
    assert (bb.x0, bb.y0, bb.x1, bb.y1) == (50, 100, 200, 120)
