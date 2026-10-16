from wr.models.identities import ChildIdentity, HouseholdSettings, TaxpayerIdentity, TaxpayerPosition, IdentityRole
from dashboard.app import _canonical_name_map, _owner_colors, _owner_style, _styled_table
from dashboard.ownership import BLUE, GREEN, PURPLE, editor_key, identity_color, table_style


def test_owner_colors_agree_with_editor_and_joint_rows():
    partners = HouseholdSettings(identities=(TaxpayerIdentity(name='Alex Example', position=TaxpayerPosition.PRIMARY), TaxpayerIdentity(name='Sam Example', position=TaxpayerPosition.SECONDARY),) + (ChildIdentity(name='Robin Example'),))
    colors = _owner_colors(partners, _canonical_name_map(partners))
    for identity in partners.identities:
        assert _owner_style(identity.name, colors) == table_style(identity_color(identity))
    assert _owner_style('Alex Example, Sam Example', colors) == table_style(PURPLE)
    assert _owner_style('Alex Example', colors, joint=True) == table_style(PURPLE)
    assert editor_key(TaxpayerPosition.PRIMARY, 'profile') == 'owner_primary_profile'
    assert editor_key(TaxpayerPosition.SECONDARY, 'name_2') == 'owner_secondary_name_2'
    assert editor_key(IdentityRole.CHILD, 'name_3') == 'owner_child_name_3'
    assert editor_key(None, 'name_4') == 'owner_unassigned_name_4'


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
