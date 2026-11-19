const express = require('express');
const app = express();
const router = express.Router();

app.use(express.json());
app.use('/api', router);

function requireAuth(req, res, next) { next(); }

router.use(requireAuth);
router.get('/users', listUsers);
router.post('/users', createUser);

function listUsers(req, res) { res.json([]); }
function createUser(req, res) { res.status(201).json({ ok: true }); }

module.exports = app;
