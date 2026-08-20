import unittest
from seqprompt.core import resolve_sequential_blocks, sequence_index_for_image, split_choices

class CoreTests(unittest.TestCase):
    def test_normal_sequence(self):
        self.assertEqual([resolve_sequential_blocks('$A|B|C$', i).text for i in range(4)], ['A','B','C','A'])
    def test_folder_sequence(self):
        r=resolve_sequential_blocks('$$A|B|C$$',1); self.assertEqual((r.text,r.folder_choices,r.matched_blocks),('B',('B',),1))
    def test_single_folder_marker(self):
        r=resolve_sequential_blocks('$$A$$',99); self.assertEqual((r.text,r.folder_choices,r.matched_blocks),('A',('A',),1))
    def test_single_folder_marker_decodes_escapes(self):
        r=resolve_sequential_blocks(r'$$A\|B$$',0); self.assertEqual((r.text,r.folder_choices),('A|B',('A|B',)))
    def test_single_dollar_without_choice_is_literal(self):
        self.assertEqual(resolve_sequential_blocks('$A$',0).text,'$A$')
    def test_multiple_blocks_share_index(self):
        self.assertEqual(resolve_sequential_blocks('$A|B$, $C|D$',1).text,'B, D')
    def test_multiple_folder_blocks(self):
        r=resolve_sequential_blocks('$$A|B$$, $$C|D$$',1); self.assertEqual(r.folder_choices,('B','D'))
    def test_old_equals_is_literal(self):
        self.assertEqual(resolve_sequential_blocks('=A|B=',1).text,'=A|B=')
    def test_old_double_equals_is_literal(self):
        self.assertEqual(resolve_sequential_blocks('==A|B==',1).text,'==A|B==')
    def test_old_brackets_are_literal(self):
        self.assertEqual(resolve_sequential_blocks('[[A|B]]',1).text,'[[A|B]]')
    def test_escaped_pipe_dollar_backslash(self):
        self.assertEqual(split_choices(r'A\|B|C\$D|E\\F'), ['A|B','C$D',r'E\F'])
    def test_unrelated_backslashes_preserved(self):
        self.assertEqual(split_choices(r'C:\models\x|D:\images\y'),[r'C:\models\x',r'D:\images\y'])
    def test_extra_network_is_atomic(self):
        self.assertEqual(resolve_sequential_blocks('$<lora:x:a|b$1>|plain$',0).text,'<lora:x:a|b$1>')
    def test_forge_alternation_pipe_is_not_choice_separator(self):
        self.assertEqual(resolve_sequential_blocks('$[red|blue] hair|green hair$',0).text,'[red|blue] hair')
    def test_sequence_inside_forge_group(self):
        self.assertEqual(resolve_sequential_blocks('($A|B$)',1).text,'(B)')
    def test_dynamic_prompt_braces_are_opaque(self):
        self.assertEqual(resolve_sequential_blocks('{$A|B$}',1).text,'{$A|B$}')
    def test_adjacent_blocks(self):
        self.assertEqual(resolve_sequential_blocks('$A|B$$C|D$',1).text,'BD')
    def test_malformed_nested_fails_literal(self):
        text='$outer $A|B$|tail$'; self.assertEqual(resolve_sequential_blocks(text,1).text,text)
    def test_malformed_nested_single_folder_fails_literal(self):
        text='$$outer $$A$$ tail$$'; self.assertEqual(resolve_sequential_blocks(text,0).text,text)
    def test_empty_choice(self):
        self.assertEqual(resolve_sequential_blocks('$A||C$',1).text,'')
    def test_currency_is_literal(self):
        self.assertEqual(resolve_sequential_blocks('price $100',1).text,'price $100')
    def test_clamp(self):
        self.assertEqual(resolve_sequential_blocks('$A|B|C$',99,'clamp').text,'C')
    def test_per_image_indices(self):
        self.assertEqual([sequence_index_for_image(i,3,'image',1,0) for i in range(5)],[0,1,2,3,4])
    def test_per_batch_indices(self):
        self.assertEqual([sequence_index_for_image(i,3,'batch',1,0) for i in range(6)],[0,0,0,1,1,1])
    def test_repeat_and_start(self):
        self.assertEqual([sequence_index_for_image(i,1,'image',2,3) for i in range(4)],[3,3,4,4])

if __name__=='__main__': unittest.main()
