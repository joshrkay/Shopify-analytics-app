// This is a test file with various edge cases

// TODO: This is a normal TODO comment
let x = 1; // TODO: inline comment

// TODO(john): Author specified
// TODO(john@email.com): Email as author 
// TODO(): Empty author
// TODO(a b c): Spaces in author

// Multiple keywords on one line: TODO FIXME HACK XXX
// TODO TODO: Double TODO

fn TodoFunction() {}  // Not a comment
struct TodoStruct {}  // Not a comment
let todo = "TODO: string literal not a comment";

// FIXME: #1234 issue reference
// TODO See issue #999 for details

// Edge case: very long description that goes on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on

// Empty description cases:
// TODO:
// TODO
// TODO:     
// FIXME

/* Multi-line comment start TODO: inside multiline */
/* TODO: another one
   spanning lines */

// Special characters in description: TODO: <script>alert('xss')</script>
// TODO: Unicode emoji 🚀🔥💯

// No colon: TODO no colon here

/*******************
 * TODO: Inside block comment with stars
 *******************/

#if 0
// TODO: inside disabled preprocessor block
#endif

// XXX(Alice)(Bob): Multiple parentheses
