from dashboard.app import _canonical_name_map, _owner_colors, _owner_style, _styled_table
from dashboard.ownership import BLUE, GREEN, PURPLE, editor_key, slot_color, table_style
from wr.models.settings import ChildSettings, PartnerSettings


def test_owner_colors_agree_with_editor_and_joint_rows():
    partners = PartnerSettings(partner_a='Alex Example', partner_b='Sam Example', children=(ChildSettings('Robin Example'),))
    colors = _owner_colors(partners, _canonical_name_map(partners))
    for slot, name in partners.identities():
        assert _owner_style(name, colors) == table_style(slot_color(slot))
    assert _owner_style('Alex Example, Sam Example', colors) == table_style(PURPLE)
    assert _owner_style('Alex Example', colors, joint=True) == table_style(PURPLE)
    assert editor_key('a', 'profile') == 'owner_a_profile'
    assert editor_key('b', 'name_2') == 'owner_b_name_2'
    assert editor_key('child_12', 'name_3') == 'owner_child_name_3'
    assert editor_key('unassigned', 'name_4') == 'owner_unassigned_name_4'


def test_non_box3_rows_are_muted_without_changing_table_values():
    rows = [{'Holder': 'Alex Example', 'Box 3': 'Yes', 'Amount': '€ 10'},
            {'Holder': 'Alex Example', 'Box 3': 'No', 'Amount': '€ 20'}]
    styles = _styled_table(rows, 'Holder', {'alex example': BLUE}, muted_rows=[False, True])
    styles._compute()
    normal = dict(styles.ctx[0, 0])
    excluded = dict(styles.ctx[1, 0])
    assert normal['background-color'] != excluded['background-color']
    assert excluded['color'] == '#b4bac4'
    assert styles.data.to_dict('records') == rows
