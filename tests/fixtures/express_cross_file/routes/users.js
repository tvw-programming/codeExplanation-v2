const express = require('express');
const router = express.Router();
router.get('/users', listUsers);
router.post('/users', createUser);
module.exports = router;
