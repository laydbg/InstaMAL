grammar Spec;

// Parser Rules
spec: (let | connect)* EOF;
number: INT | FLOAT;

expr: sign? term ((PLUS | MINUS) term)*;
sign: (PLUS | MINUS);
term: fact ((TIMES | DIVIDE) fact)*;
fact: prim (POWER prim)?;
prim: number | LPAREN expr RPAREN | distributionSample;
distributionSample: ID LPAREN parameters RPAREN;
parameters: expr (COMMA expr)*;

let: LET variable ASSIGN assetSet SEMICOLON;
variable: ID;
assetSet: variable | assetInstantiation;
assetInstantiation: ID LPAREN expr? RPAREN;

connect: CONNECT LCURLY connectionRule* RCURLY;
connectionRule:
	number COLON assetSet RARROW associationFieldname assetSet SEMICOLON;

associationFieldname: LSQUARE ID RSQUARE;

// spec: (include | define | let | associate | subsystem | connect)* EOF;
// include: INCLUDE STRING SEMICOLON;
// define: HASH ID COLON STRING;
// number: INT | FLOAT;
// 
// expr: sign? term ((PLUS | MINUS) term)*;
// sign: (PLUS | MINUS);
// term: fact ((TIMES | DIVIDE) fact)*;
// fact: prim (POWER prim)?;
// prim: number | LPAREN expr RPAREN | distributionSample;
// distributionSample: ID LPAREN parameters RPAREN;
// parameters: expr (COMMA expr)*;
// 
// let: LET variable ASSIGN assetSet SEMICOLON;
// variable: ID;
// assetSet: variable | assetInstantiation | subsystemSetAccess;
// assetInstantiation: ID LPAREN expr? RPAREN;
// subsystemSetAccess: ID (DOT ID)+;
// 
// associate: assetSet RARROW associationFieldname assetSet SEMICOLON;
// associationFieldname: LSQUARE ID RSQUARE;
// 
// subsystem:
// 	SUBSYSTEM ID LCURLY (let | associate | connect | subsystemAssign)* RCURLY;
// subsystemAssign: subsystemSetAccess ASSIGN assetSet SEMICOLON;
// 
// connect: CONNECT LCURLY connectionRule* RCURLY;
// connectionRule: number COLON associate;

// Lexer Rules
INCLUDE: 'include';
LET: 'let';
SUBSYSTEM: 'subsystem';
CONNECT: 'connect';

STRING: '"' .*? '"';
INT: [0-9]+;
FLOAT: [0-9]* DOT [0-9]+;
ID: [a-zA-Z0-9_]+;

LPAREN: '(';
RPAREN: ')';
LCURLY: '{';
RCURLY: '}';
LSQUARE: '[';
RSQUARE: ']';
HASH: '#';
COLON: ':';
SEMICOLON: ';';
RARROW: '-->';
ASSIGN: '=';
DOT: '.';
COMMA: ',';
PLUS: '+';
MINUS: '-';
TIMES: '*';
DIVIDE: '/';
POWER: '^';
// INTERSECT: '/\\';
// UNION: '\\/';

COMMENT: '//' ~[\r\n]* -> skip;
ML_COMMENT: '/*' .*? '*/' -> skip;
WS: [ \t\r\n] -> skip;