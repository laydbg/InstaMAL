grammar Spec;

// Parser Rules
spec: (param | subsystem | let | connect)* prune? EOF;
param: PARAM ID (ASSIGN | TILDE) expr SEMICOLON;
number: INT | FLOAT;

expr: sign? term ((PLUS | MINUS) term)*;
sign: (PLUS | MINUS);
term: fact ((TIMES | DIVIDE) fact)*;
fact: prim (POWER prim)?;
prim: number | LPAREN expr RPAREN | distributionSample | ID;
distributionSample: ID LPAREN parameters RPAREN;
parameters: expr (COMMA expr)*;

subsystem: SUBSYSTEM ID LCURLY (let | connect)* RCURLY;
subsystemSetAccess: ID (DOT ID)+;

let: LET variable ASSIGN assetSet SEMICOLON;
variable: ID;
assetSet: namedAssetSet | assetInstantiation;
namedAssetSet: variable | subsystemSetAccess;
assetInstantiation: ID LPAREN expr? RPAREN;

connect: CONNECT LCURLY connectionRule* RCURLY;
connectionRule:
	number COLON assetSet RARROW associationFieldname assetSet SEMICOLON;
associationFieldname: LSQUARE ID RSQUARE;

prune: PRUNE (LPAREN pruneParameters? RPAREN)? SEMICOLON;
pruneParameters: namedAssetSet (COMMA namedAssetSet)*;

// Lexer Rules
PARAM: 'param';
LET: 'let';
SUBSYSTEM: 'subsystem';
CONNECT: 'connect';
PRUNE: 'prune';

INT: [0-9]+;
FLOAT: [0-9]* DOT [0-9]+;
ID: [a-zA-Z0-9_]+;

LPAREN: '(';
RPAREN: ')';
LCURLY: '{';
RCURLY: '}';
LSQUARE: '[';
RSQUARE: ']';
COLON: ':';
SEMICOLON: ';';
RARROW: '-->';
ASSIGN: '=';
TILDE: '~';
DOT: '.';
COMMA: ',';
PLUS: '+';
MINUS: '-';
TIMES: '*';
DIVIDE: '/';
POWER: '^';

COMMENT: '//' ~[\r\n]* -> skip;
ML_COMMENT: '/*' .*? '*/' -> skip;
WS: [ \t\r\n] -> skip;
