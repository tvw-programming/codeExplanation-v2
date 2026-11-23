const express = require('express');
const app = express();
app.use('/api', require('./routes/users'));
module.exports = app;
