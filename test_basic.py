def test_map_paper_type_major():
    from paper_sync import map_paper_type
    paper = {"group_code": "MAJOR", "group_type": "core"}
    assert map_paper_type(paper) == "DSC"

def test_is_bachelor_bca():
    from paper_sync import is_bachelor
    assert is_bachelor("BCA") == True

def test_is_bachelor_mca():
    from paper_sync import is_bachelor
    assert is_bachelor("MCA") == False